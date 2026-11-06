from collections.abc import Iterable
from typing import Iterator

from .errors import LLMError
from .protocol import (
    LLMMessage,
    LLMResponse,
    LLMStreamCompleted,
    LLMStreamEvent,
    LLMTextDelta,
    validate_scripted_stream,
)


class FakeLLMClient:
    """Deterministic, network-free implementation for tests and local use."""

    def __init__(
        self,
        response: LLMResponse | None = None,
        *,
        stream_events: Iterable[LLMStreamEvent] | None = None,
        completion_error: LLMError | None = None,
        stream_error: LLMError | None = None,
    ) -> None:
        self.response = response or LLMResponse(
            text="Fake response", model="fake"
        )
        self._stream_events: tuple[LLMStreamEvent, ...] = (
            tuple(stream_events)
            if stream_events is not None
            else (
                LLMTextDelta(self.response.text),
                LLMStreamCompleted(self.response),
            )
        )
        self.completion_error = completion_error
        self.stream_error = stream_error

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        if self.completion_error is not None:
            raise self.completion_error
        return self.response

    def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Iterator[LLMStreamEvent]:
        if self.stream_error is not None:
            raise self.stream_error
        validate_scripted_stream(self._stream_events)
        return iter(self._stream_events)
