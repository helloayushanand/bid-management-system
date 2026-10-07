"""Company-context providers used by the assessment pipeline."""

from company_context.synthetic_profile import (
    SYNTHETIC_COMPANY_PROFILE,
    SYNTHETIC_CONTEXT_WARNING,
    get_synthetic_company_profile,
    get_synthetic_context_warning,
    validate_synthetic_profile,
)

__all__ = [
    "SYNTHETIC_COMPANY_PROFILE",
    "SYNTHETIC_CONTEXT_WARNING",
    "get_synthetic_company_profile",
    "get_synthetic_context_warning",
    "validate_synthetic_profile",
]