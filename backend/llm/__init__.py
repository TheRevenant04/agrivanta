from typing import TYPE_CHECKING

from .fake import FakeLLMClient
from .protocol import (
    LLMClient,
    LLMMessage,
    LLMResponse,
    LLMStreamCompleted,
    LLMStreamEvent,
    LLMTextDelta,
)
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

if TYPE_CHECKING:
    from .openai_adapter import OpenAIResponsesClient


def __getattr__(name: str):
    if name == "OpenAIResponsesClient":
        from .openai_adapter import OpenAIResponsesClient

        return OpenAIResponsesClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "FakeLLMClient",
    "LLMAuthenticationError",
    "LLMClient",
    "LLMConfigurationError",
    "LLMError",
    "LLMMessage",
    "LLMMalformedResponseError",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMStreamCompleted",
    "LLMStreamError",
    "LLMStreamEvent",
    "LLMTextDelta",
    "LLMTimeoutError",
    "OpenAIResponsesClient",
]
