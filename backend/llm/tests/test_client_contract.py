from types import SimpleNamespace
from unittest.mock import Mock

import openai
import pytest
from django.test import override_settings

from llm import (
    FakeLLMClient,
    LLMAuthenticationError,
    LLMClient,
    LLMConfigurationError,
    LLMMessage,
    LLMMalformedResponseError,
    LLMRateLimitError,
    LLMResponse,
    LLMStreamCompleted,
    LLMStreamError,
    LLMTextDelta,
    LLMTimeoutError,
    OpenAIResponsesClient,
)

MESSAGES = [LLMMessage(role="user", content="Hello")]
RESPONSE = LLMResponse(
    text="Hello there", model="test-model", input_tokens=3, output_tokens=2
)


def _provider_response(
    response: LLMResponse = RESPONSE,
) -> SimpleNamespace:
    return SimpleNamespace(
        output_text=response.text,
        model=response.model,
        usage=SimpleNamespace(
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        ),
    )


def _openai_client(create: Mock) -> SimpleNamespace:
    return SimpleNamespace(responses=SimpleNamespace(create=create))


def _assert_contract(client: LLMClient) -> None:
    assert client.complete(MESSAGES) == RESPONSE
    events = list(client.stream(MESSAGES))
    assert events == [
        LLMTextDelta("Hello "),
        LLMTextDelta("there"),
        LLMStreamCompleted(RESPONSE),
    ]
    assert "".join(
        event.text for event in events if isinstance(event, LLMTextDelta)
    ) == RESPONSE.text
    assert sum(isinstance(event, LLMStreamCompleted) for event in events) == 1


def test_fake_implements_provider_neutral_contract() -> None:
    client = FakeLLMClient(
        RESPONSE,
        stream_events=(
            LLMTextDelta("Hello "),
            LLMTextDelta("there"),
            LLMStreamCompleted(RESPONSE),
        ),
    )

    _assert_contract(client)


def test_openai_adapter_implements_provider_neutral_contract() -> None:
    create = Mock(
        side_effect=[
            _provider_response(),
            iter(
                [
                    SimpleNamespace(type="response.output_text.delta", delta="Hello "),
                    SimpleNamespace(type="response.output_text.delta", delta="there"),
                    SimpleNamespace(
                        type="response.completed",
                        response=_provider_response(),
                    ),
                ]
            ),
        ]
    )
    client = OpenAIResponsesClient(
        "test-key", "test-model", client=_openai_client(create)
    )

    _assert_contract(client)

    assert create.call_args_list[0].kwargs == {
        "model": "test-model",
        "input": [{"role": "user", "content": "Hello"}],
    }
    assert create.call_args_list[1].kwargs["stream"] is True


def test_fake_can_script_a_typed_failure_for_each_operation() -> None:
    client = FakeLLMClient(
        RESPONSE,
        completion_error=LLMRateLimitError("limited"),
        stream_error=LLMTimeoutError("timed out"),
    )

    with pytest.raises(LLMRateLimitError, match="limited"):
        client.complete(MESSAGES)
    with pytest.raises(LLMTimeoutError, match="timed out"):
        list(client.stream(MESSAGES))


def test_fake_rejects_stream_without_completion_or_matching_deltas() -> None:
    no_completion = FakeLLMClient(
        RESPONSE,
        stream_events=(LLMTextDelta(RESPONSE.text),),
    )
    mismatched = FakeLLMClient(
        RESPONSE,
        stream_events=(
            LLMTextDelta("different"),
            LLMStreamCompleted(RESPONSE),
        ),
    )

    with pytest.raises(LLMStreamError):
        list(no_completion.stream(MESSAGES))
    with pytest.raises(LLMStreamError):
        list(mismatched.stream(MESSAGES))


@pytest.mark.parametrize(
    ("provider_error", "interface_error"),
    [
        (
            openai.APITimeoutError(request=Mock()),
            LLMTimeoutError,
        ),
        (
            openai.RateLimitError(
                "rate limited",
                response=Mock(status_code=429),
                body=None,
            ),
            LLMRateLimitError,
        ),
        (
            openai.AuthenticationError(
                "unauthorized",
                response=Mock(status_code=401),
                body=None,
            ),
            LLMAuthenticationError,
        ),
    ],
)
def test_openai_provider_errors_are_translated(
    provider_error: Exception,
    interface_error: type[Exception],
) -> None:
    client = OpenAIResponsesClient(
        "test-key",
        "test-model",
        client=_openai_client(Mock(side_effect=provider_error)),
    )

    with pytest.raises(interface_error) as raised:
        client.complete(MESSAGES)

    assert raised.value.__cause__ is provider_error


def test_openai_rejects_missing_credentials_with_typed_error() -> None:
    client = OpenAIResponsesClient("", "test-model")

    with pytest.raises(LLMConfigurationError):
        client.complete(MESSAGES)


def test_openai_translates_malformed_responses() -> None:
    client = OpenAIResponsesClient(
        "test-key",
        "test-model",
        client=_openai_client(Mock(return_value=SimpleNamespace(output_text=123))),
    )

    with pytest.raises(LLMMalformedResponseError):
        client.complete(MESSAGES)


def test_openai_normalization_uses_requested_model_when_response_omits_it() -> None:
    client = OpenAIResponsesClient(
        "test-key",
        "test-model",
        client=_openai_client(
            Mock(
                return_value=SimpleNamespace(
                    output_text="normalized text",
                    model=None,
                    usage=None,
                )
            )
        ),
    )

    assert client.complete(MESSAGES) == LLMResponse(
        text="normalized text", model="test-model"
    )


def test_openai_stream_without_completion_is_an_error() -> None:
    client = OpenAIResponsesClient(
        "test-key",
        "test-model",
        client=_openai_client(
            Mock(
                return_value=iter(
                    [
                        SimpleNamespace(
                            type="response.output_text.delta", delta="partial"
                        )
                    ]
                )
            )
        ),
    )

    with pytest.raises(LLMStreamError):
        list(client.stream(MESSAGES))


@pytest.mark.parametrize(
    ("provider_code", "interface_error"),
    [
        ("rate_limit_exceeded", LLMRateLimitError),
        ("invalid_api_key", LLMAuthenticationError),
        ("request_timeout", LLMTimeoutError),
    ],
)
def test_openai_stream_failure_events_are_typed(
    provider_code: str,
    interface_error: type[Exception],
) -> None:
    client = OpenAIResponsesClient(
        "test-key",
        "test-model",
        client=_openai_client(
            Mock(
                return_value=iter(
                    [
                        SimpleNamespace(
                            type="response.failed",
                            error={"code": provider_code},
                        )
                    ]
                )
            )
        ),
    )

    with pytest.raises(interface_error):
        list(client.stream(MESSAGES))


def test_settings_supply_openai_model_and_credentials() -> None:
    with override_settings(
        LLM_OPENAI_API_KEY="from-environment",
        LLM_OPENAI_MODEL="configured-model",
    ):
        client = OpenAIResponsesClient.from_settings()

    assert client._api_key == "from-environment"
    assert client._model == "configured-model"
