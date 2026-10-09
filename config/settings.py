"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_environment() -> None:
    """Load local environment variables without replacing existing ones."""

    load_dotenv(dotenv_path=ENV_FILE, override=False)


def get_required_environment_variable(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(
            f"Required environment variable '{name}' is not configured."
        )
    return value


def get_integer_environment_variable(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"'{name}' must be an integer.") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"'{name}' must be at least {minimum}.")
    return value


def get_float_environment_variable(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"'{name}' must be numeric.") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"'{name}' must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"'{name}' must not exceed {maximum}.")
    return value


def get_boolean_environment_variable(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, str(default)).strip().lower()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"'{name}' must be true or false.")


@dataclass(frozen=True)
class GroqSettings:
    """Configuration used by the Groq LLM adapter."""

    api_key: str
    model: str
    response_mode: str = "json_object"
    temperature: float = 0.0
    max_completion_tokens: int = 900
    max_retries: int = 3
    rate_limit_max_retries: int = 5
    request_timeout_seconds: float = 120.0
    min_request_interval_seconds: float = 15.0
    rate_limit_fallback_seconds: float = 60.0
    structured_output_strict: bool = False

    @classmethod
    def from_environment(cls) -> "GroqSettings":
        load_environment()
        response_mode = os.getenv(
            "GROQ_RESPONSE_MODE", "json_object"
        ).strip().lower()
        valid_modes = {"json_object", "json_schema"}
        if response_mode not in valid_modes:
            raise ValueError(
                "GROQ_RESPONSE_MODE must be json_object or json_schema."
            )

        return cls(
            api_key=get_required_environment_variable("GROQ_API_KEY"),
            model=get_required_environment_variable("GROQ_MODEL"),
            response_mode=response_mode,
            temperature=get_float_environment_variable(
                "GROQ_TEMPERATURE", 0.0, minimum=0.0, maximum=2.0
            ),
            max_completion_tokens=get_integer_environment_variable(
                "GROQ_MAX_COMPLETION_TOKENS",
                900,
                minimum=100,
            ),
            max_retries=get_integer_environment_variable(
                "GROQ_MAX_RETRIES", 3, minimum=0
            ),
            rate_limit_max_retries=get_integer_environment_variable(
                "GROQ_RATE_LIMIT_MAX_RETRIES", 5, minimum=0
            ),
            request_timeout_seconds=get_float_environment_variable(
                "GROQ_REQUEST_TIMEOUT_SECONDS", 120.0, minimum=1.0
            ),
            min_request_interval_seconds=get_float_environment_variable(
                "GROQ_MIN_REQUEST_INTERVAL_SECONDS", 15.0, minimum=0.0
            ),
            rate_limit_fallback_seconds=get_float_environment_variable(
                "GROQ_RATE_LIMIT_FALLBACK_SECONDS", 60.0, minimum=1.0
            ),
            structured_output_strict=get_boolean_environment_variable(
                "GROQ_STRUCTURED_OUTPUT_STRICT", False
            ),
        )


@dataclass(frozen=True)
class AnalysisSettings:
    """Configuration for tender chunking and analysis."""

    maximum_chunk_characters: int = 5000
    overlap_pages: int = 0
    maximum_excerpt_characters: int = 300
    minimum_page_characters: int = 20

    @classmethod
    def from_environment(cls) -> "AnalysisSettings":
        load_environment()
        return cls(
            maximum_chunk_characters=get_integer_environment_variable(
                "ANALYSIS_MAX_CHUNK_CHARACTERS", 5000, minimum=1000
            ),
            overlap_pages=get_integer_environment_variable(
                "ANALYSIS_OVERLAP_PAGES", 0, minimum=0
            ),
            maximum_excerpt_characters=get_integer_environment_variable(
                "ANALYSIS_MAX_EXCERPT_CHARACTERS", 300, minimum=50
            ),
            minimum_page_characters=get_integer_environment_variable(
                "ANALYSIS_MINIMUM_PAGE_CHARACTERS", 20, minimum=0
            ),
        )
