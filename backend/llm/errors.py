class LLMError(Exception):
    """Base class for failures exposed by the provider-neutral LLM contract."""


class LLMConfigurationError(LLMError):
    """Provider configuration is missing or invalid."""


class LLMAuthenticationError(LLMError):
    """The provider rejected the configured credentials."""


class LLMRateLimitError(LLMError):
    """The provider rejected the request because of rate limiting."""


class LLMTimeoutError(LLMError):
    """The provider request timed out."""


class LLMProviderError(LLMError):
    """The provider request failed for a reason other than timeout or rate limit."""


class LLMMalformedResponseError(LLMError):
    """The provider returned data that cannot be normalized."""


class LLMStreamError(LLMError):
    """The provider stream ended without a valid final completion."""
