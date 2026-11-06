from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import openai
from openai import OpenAI

from .errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
    LLMMalformedResponseError,
    LLMProviderError,
    LLMRateLimitError,
    LLMStreamError,
    LLMTimeoutError,
)
from .protocol import (
    LLMMessage,
    LLMResponse,
    LLMStreamCompleted,
    LLMStreamEvent,
    LLMTextDelta,
)


@contextmanager
def _translate_provider_errors():
    try:
        yield
    except LLMError:
        raise
    except openai.APITimeoutError as exc:
        raise LLMTimeoutError("The LLM provider request timed out.") from exc
    except openai.RateLimitError as exc:
        raise LLMRateLimitError("The LLM provider rate limit was exceeded.") from exc
    except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
        raise LLMAuthenticationError(
            "The LLM provider rejected the configured credentials."
        ) from exc
    except openai.APIStatusError as exc:
        if exc.status_code in (401, 403):
            raise LLMAuthenticationError(
                "The LLM provider rejected the configured credentials."
            ) from exc
        raise LLMProviderError("The LLM provider request failed.") from exc
    except openai.OpenAIError as exc:
        raise LLMProviderError("The LLM provider request failed.") from exc


class OpenAIResponsesClient:
    """OpenAI Responses API adapter implementing the provider-neutral contract."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    @classmethod
    def from_settings(cls) -> "OpenAIResponsesClient":
        from django.conf import settings

        return cls(
            api_key=settings.LLM_OPENAI_API_KEY,
            model=settings.LLM_OPENAI_MODEL,
        )

    def _get_client(self) -> Any:
        if not self._api_key:
            raise LLMConfigurationError("OPENAI_API_KEY is not configured.")
        if not self._model:
            raise LLMConfigurationError("OPENAI_MODEL is not configured.")
        if self._client is None:
            try:
                self._client = OpenAI(api_key=self._api_key)
            except openai.OpenAIError as exc:
                raise LLMConfigurationError(
                    "The OpenAI client could not be configured."
                ) from exc
        return self._client

    def _request(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None,
        max_output_tokens: int | None,
        temperature: float | None,
        stream: bool,
    ) -> dict[str, Any]:
        if not messages:
            raise LLMConfigurationError("At least one message is required.")
        selected_model = model or self._model
        if not selected_model:
            raise LLMConfigurationError("OPENAI_MODEL is not configured.")

        request: dict[str, Any] = {
            "model": selected_model,
            "input": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        }
        if max_output_tokens is not None:
            request["max_output_tokens"] = max_output_tokens
        if temperature is not None:
            request["temperature"] = temperature
        if stream:
            request["stream"] = True
        return request

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        request = self._request(
            messages,
            model=model,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            stream=False,
        )
        client = self._get_client()
        with _translate_provider_errors():
            response = client.responses.create(**request)
            return _normalize_response(response, request["model"])

    def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Iterator[LLMStreamEvent]:
        request = self._request(
            messages,
            model=model,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            stream=True,
        )
        client = self._get_client()

        def events() -> Iterator[LLMStreamEvent]:
            delta_text: list[str] = []
            completed = False
            with _translate_provider_errors():
                for event in client.responses.create(**request):
                    event_type = getattr(event, "type", None)
                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", None)
                        if not isinstance(delta, str):
                            raise LLMMalformedResponseError(
                                "The provider returned a malformed text delta."
                            )
                        delta_text.append(delta)
                        yield LLMTextDelta(delta)
                    elif event_type == "response.completed":
                        if completed:
                            raise LLMStreamError(
                                "The provider returned multiple completion events."
                            )
                        response = _normalize_response(
                            getattr(event, "response", None), request["model"]
                        )
                        if "".join(delta_text) != response.text:
                            raise LLMMalformedResponseError(
                                "Stream deltas do not match the final response."
                            )
                        completed = True
                        yield LLMStreamCompleted(response)
                        return
                    elif event_type in ("response.failed", "error"):
                        raise _stream_failure(event)
            if not completed:
                raise LLMStreamError(
                    "The LLM provider stream ended without a completion event."
                )

        return events()


def _stream_failure(event: Any) -> LLMError:
    provider_error = getattr(event, "error", None)
    if isinstance(provider_error, dict):
        code = provider_error.get("code") or provider_error.get("type")
    else:
        code = getattr(provider_error, "code", None) or getattr(
            provider_error, "type", None
        )
    if code in ("rate_limit", "rate_limit_error", "rate_limit_exceeded"):
        return LLMRateLimitError("The LLM provider rate limit was exceeded.")
    if code in ("authentication_error", "invalid_api_key", "permission_denied"):
        return LLMAuthenticationError(
            "The LLM provider rejected the configured credentials."
        )
    if code in ("timeout", "request_timeout"):
        return LLMTimeoutError("The LLM provider request timed out.")
    return LLMProviderError("The LLM provider stream failed.")


def _normalize_response(response: Any, requested_model: str) -> LLMResponse:
    try:
        text = response.output_text
        model = response.model or requested_model
        usage = response.usage
        input_tokens = usage.input_tokens if usage is not None else None
        output_tokens = usage.output_tokens if usage is not None else None
        if not isinstance(text, str) or not isinstance(model, str) or not model:
            raise ValueError("Missing normalized text or model.")
        if input_tokens is not None and (
            not isinstance(input_tokens, int) or input_tokens < 0
        ):
            raise ValueError("Invalid input token count.")
        if output_tokens is not None and (
            not isinstance(output_tokens, int) or output_tokens < 0
        ):
            raise ValueError("Invalid output token count.")
        return LLMResponse(
            text=text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise LLMMalformedResponseError(
            "The LLM provider returned a malformed completion response."
        ) from exc
