"""Provider-neutral interfaces for structured LLM calls."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from pydantic import BaseModel


ResponseModelT = TypeVar(
    "ResponseModelT",
    bound=BaseModel,
)


@dataclass(frozen=True)
class LLMTokenUsage:
    """Token usage reported by an LLM provider."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return token usage as a serializable dictionary."""

        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class StructuredLLMResponse(Generic[ResponseModelT]):
    """Validated structured response returned by an LLM adapter."""

    parsed: ResponseModelT
    model: str
    usage: LLMTokenUsage = field(
        default_factory=LLMTokenUsage,
    )
    request_id: str | None = None
    raw_text: str | None = None
    attempt_count: int = 1


class LLMAdapterError(RuntimeError):
    """Base error raised by an LLM adapter."""


class LLMConfigurationError(LLMAdapterError):
    """Raised when required adapter configuration is invalid."""


class LLMResponseError(LLMAdapterError):
    """Raised when an LLM response cannot be validated."""


class LLMProviderError(LLMAdapterError):
    """Raised when the external LLM provider rejects or fails a request."""


class BaseLLMAdapter(ABC):
    """Abstract interface implemented by every LLM provider adapter."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the configured provider model identifier."""

    @abstractmethod
    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseModelT],
        schema_name: str,
    ) -> StructuredLLMResponse[ResponseModelT]: 
        """
        Generate and validate a structured model response.

        Implementations must validate the provider response against the
        supplied Pydantic response model before returning it.
        """

    def health_check(self) -> bool:
        """
        Return whether adapter configuration appears usable.

        Provider implementations may override this with an API-level check.
        """

        return bool(self.model_name)