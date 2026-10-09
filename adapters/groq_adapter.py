"""Groq adapter using JSON Object Mode and local validation."""

from __future__ import annotations

import json
import random
import re
from copy import deepcopy
from time import monotonic, sleep
from typing import Any, TypeVar

from groq import BadRequestError, Groq, RateLimitError
from pydantic import BaseModel, ValidationError

from adapters.base_llm import (
    BaseLLMAdapter,
    LLMConfigurationError,
    LLMProviderError,
    LLMResponseError,
    LLMTokenUsage,
    StructuredLLMResponse,
)
from config import GroqSettings


ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)
_SCHEMA_NOISE_KEYS = {"title", "description", "examples", "default"}


class GroqAdapter(BaseLLMAdapter):
    """Generate JSON with Groq and validate it locally with Pydantic."""

    def __init__(self, settings: GroqSettings | None = None) -> None:
        self.settings = settings or GroqSettings.from_environment()
        if not self.settings.api_key:
            raise LLMConfigurationError("GROQ_API_KEY is not configured.")
        if not self.settings.model:
            raise LLMConfigurationError("GROQ_MODEL is not configured.")

        self.client = Groq(
            api_key=self.settings.api_key,
            timeout=self.settings.request_timeout_seconds,
            max_retries=0,
        )
        self._last_request_started_at: float | None = None

    @property
    def model_name(self) -> str:
        return self.settings.model

    @staticmethod
    def _compact_schema_value(value: Any) -> Any:
        """Remove nonessential schema metadata to reduce prompt tokens."""

        if isinstance(value, dict):
            return {
                key: GroqAdapter._compact_schema_value(item)
                for key, item in value.items()
                if key not in _SCHEMA_NOISE_KEYS
            }
        if isinstance(value, list):
            return [
                GroqAdapter._compact_schema_value(item)
                for item in value
            ]
        return value

    def _compact_schema(
        self,
        response_model: type[ResponseModelT],
    ) -> dict[str, Any]:
        schema = deepcopy(response_model.model_json_schema())
        return self._compact_schema_value(schema)

    def _build_response_format(
        self,
        *,
        response_model: type[ResponseModelT],
        schema_name: str,
    ) -> dict[str, Any]:
        if self.settings.response_mode == "json_object":
            return {"type": "json_object"}

        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name.strip(),
                "strict": self.settings.structured_output_strict,
                "schema": response_model.model_json_schema(),
            },
        }

    def _build_schema_instruction(
        self,
        *,
        user_prompt: str,
        response_model: type[ResponseModelT],
    ) -> str:
        """Append a compact target schema for JSON Object Mode."""

        if self.settings.response_mode != "json_object":
            return user_prompt

        schema_text = json.dumps(
            self._compact_schema(response_model),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            f"{user_prompt}\n\n"
            "OUTPUT REQUIREMENTS:\n"
            "Return exactly one valid JSON object and nothing else.\n"
            "Do not use Markdown code fences.\n"
            "Use null for unknown optional values.\n"
            "Use empty arrays when no list items are found.\n"
            "The JSON must validate against this compact schema:\n"
            f"{schema_text}"
        )

    def _apply_request_spacing(self) -> None:
        now = monotonic()
        if self._last_request_started_at is not None:
            remaining = (
                self.settings.min_request_interval_seconds
                - (now - self._last_request_started_at)
            )
            if remaining > 0:
                sleep(remaining)
        self._last_request_started_at = monotonic()

    @staticmethod
    def _extract_message_content(completion: Any) -> str:
        choices = getattr(completion, "choices", None)
        if not choices:
            raise LLMResponseError("Groq returned no completion choices.")
        content = getattr(choices[0].message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("Groq returned empty message content.")
        return content.strip()

    @staticmethod
    def _extract_token_usage(completion: Any) -> LLMTokenUsage:
        usage = getattr(completion, "usage", None)
        if usage is None:
            return LLMTokenUsage()
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(
            getattr(usage, "total_tokens", input_tokens + output_tokens)
            or 0
        )
        return LLMTokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _extract_request_id(completion: Any) -> str | None:
        value = getattr(completion, "id", None)
        return str(value) if value is not None else None

    def _extract_retry_after_seconds(self, exc: RateLimitError) -> float:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if headers is not None:
            raw_value = headers.get("retry-after")
            if raw_value:
                try:
                    return max(float(raw_value), 1.0)
                except (TypeError, ValueError):
                    pass

        match = re.search(
            r"try again in\s+([0-9]+(?:\.[0-9]+)?)s",
            str(exc),
            flags=re.IGNORECASE,
        )
        if match:
            return max(float(match.group(1)), 1.0)
        return self.settings.rate_limit_fallback_seconds

    @staticmethod
    def _validation_error_text(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            return json.dumps(exc.errors(), ensure_ascii=False)
        return str(exc)

    def _build_repair_prompt(
        self,
        *,
        original_prompt: str,
        previous_output: str,
        validation_error: str,
        response_model: type[ResponseModelT],
    ) -> str:
        """Build a repair request using the failed output and error details."""

        schema_text = json.dumps(
            self._compact_schema(response_model),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            "Repair the previous JSON response. Return only corrected JSON.\n"
            "Do not add facts that were not present in the original task.\n\n"
            f"ORIGINAL TASK:\n{original_prompt}\n\n"
            f"PREVIOUS OUTPUT:\n{previous_output}\n\n"
            f"VALIDATION ERROR:\n{validation_error}\n\n"
            f"TARGET SCHEMA:\n{schema_text}"
        )

    def _make_completion(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_format: dict[str, Any],
    ) -> Any:
        self._apply_request_spacing()
        request_arguments: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.temperature,
            "max_completion_tokens": (
                self.settings.max_completion_tokens
            ),
            "response_format": response_format,
            "stream": False,
        }

        if self.settings.model.startswith("qwen/"):
            request_arguments["reasoning_effort"] = "none"

        return self.client.chat.completions.create(**request_arguments)

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseModelT],
        schema_name: str,
    ) -> StructuredLLMResponse[ResponseModelT]:
        if not system_prompt.strip() or not user_prompt.strip():
            raise ValueError("System and user prompts must not be empty.")

        response_format = self._build_response_format(
            response_model=response_model,
            schema_name=schema_name,
        )
        original_prompt = self._build_schema_instruction(
            user_prompt=user_prompt,
            response_model=response_model,
        )
        current_prompt = original_prompt
        rate_failures = 0
        provider_failures = 0
        validation_failures = 0
        total_attempts = 0
        last_raw_text = ""

        while True:
            total_attempts += 1
            try:
                completion = self._make_completion(
                    system_prompt=system_prompt,
                    user_prompt=current_prompt,
                    response_format=response_format,
                )
                last_raw_text = self._extract_message_content(completion)
                parsed_json = json.loads(last_raw_text)
                parsed = response_model.model_validate(parsed_json)

                return StructuredLLMResponse(
                    parsed=parsed,
                    model=self.settings.model,
                    usage=self._extract_token_usage(completion),
                    request_id=self._extract_request_id(completion),
                    raw_text=last_raw_text,
                    attempt_count=total_attempts,
                )

            except RateLimitError as exc:
                error_text = str(exc).lower()
                if (
                    "request too large" in error_text
                    or "expected output tokens exceed" in error_text
                ):
                    raise LLMProviderError(
                        "Groq rejected the request because the configured "
                        "maximum completion tokens exceed the account OTPM "
                        "limit. Reduce GROQ_MAX_COMPLETION_TOKENS. "
                        f"Current value: "
                        f"{self.settings.max_completion_tokens}. "
                        f"Provider error: {exc}"
                    ) from exc

                rate_failures += 1
                if rate_failures > self.settings.rate_limit_max_retries:
                    raise LLMProviderError(
                        "Groq rate limit remained unavailable after "
                        f"{rate_failures} retries: {exc}"
                    ) from exc
                sleep(
                    self._extract_retry_after_seconds(exc)
                    + random.uniform(0.5, 2.0)
                )

            except (json.JSONDecodeError, ValidationError, LLMResponseError) as exc:
                validation_failures += 1
                if validation_failures > self.settings.max_retries:
                    raise LLMResponseError(
                        "Groq returned JSON that did not match the local "
                        f"Pydantic model after {validation_failures} retries. "
                        f"Last error: {exc}"
                    ) from exc
                current_prompt = self._build_repair_prompt(
                    original_prompt=original_prompt,
                    previous_output=last_raw_text,
                    validation_error=self._validation_error_text(exc),
                    response_model=response_model,
                )

            except BadRequestError as exc:
                provider_failures += 1
                if provider_failures > self.settings.max_retries:
                    raise LLMProviderError(
                        "Groq rejected the request after "
                        f"{provider_failures} retries: {exc}"
                    ) from exc
                if "json_validate_failed" in str(exc):
                    response_format = {"type": "json_object"}
                    current_prompt = self._build_schema_instruction(
                        user_prompt=user_prompt,
                        response_model=response_model,
                    )
                sleep(min(2 ** provider_failures, 8))

            except Exception as exc:
                provider_failures += 1
                if provider_failures > self.settings.max_retries:
                    raise LLMProviderError(
                        "Groq request failed after "
                        f"{provider_failures} retries: {exc}"
                    ) from exc
                sleep(min(2 ** provider_failures, 8))
