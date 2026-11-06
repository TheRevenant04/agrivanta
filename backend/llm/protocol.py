from dataclasses import dataclass
from typing import Iterator, Literal, Protocol, TypeAlias

from .errors import LLMStreamError

MessageRole: TypeAlias = Literal["system", "developer", "user", "assistant"]


@dataclass(frozen=True)
class LLMMessage:
    """A provider-independent message in a completion conversation."""

    role: MessageRole
    content: str


@dataclass(frozen=True)
class LLMResponse:
    """Normalized final text and optional usage returned by an LLM."""

    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class LLMTextDelta:
    """One ordered text fragment emitted during a streaming completion."""

    text: str


@dataclass(frozen=True)
class LLMStreamCompleted:
    """The final normalized response for a completed stream."""

    response: LLMResponse


LLMStreamEvent: TypeAlias = LLMTextDelta | LLMStreamCompleted


class LLMClient(Protocol):
    """Provider-neutral interface for non-streaming and streaming completion."""

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse: ...

    def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Iterator[LLMStreamEvent]: ...


def validate_scripted_stream(events: tuple[LLMStreamEvent, ...]) -> None:
    completions = [
        (index, event)
        for index, event in enumerate(events)
        if isinstance(event, LLMStreamCompleted)
    ]
    if len(completions) != 1 or completions[0][0] != len(events) - 1:
        raise LLMStreamError(
            "A stream must end with exactly one completion event."
        )
    if any(not isinstance(event, LLMTextDelta) for event in events[:-1]):
        raise LLMStreamError("Only text deltas may precede the completion event.")
    if any(not isinstance(event.text, str) for event in events[:-1]):
        raise LLMStreamError("A stream contains a non-text delta.")

    response = completions[0][1].response
    if "".join(event.text for event in events[:-1]) != response.text:
        raise LLMStreamError(
            "Concatenated text deltas do not match the final response."
        )
