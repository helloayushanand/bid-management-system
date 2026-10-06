"""Shared utility functions for the bid management portal."""

from utils.file_utils import (
    build_download_filename,
    calculate_sha256,
    output_stem,
    read_binary_file,
    result_to_json_bytes,
    result_to_text,
    result_to_text_bytes,
    sanitize_filename,
)
from utils.text_utils import (
    calculate_alphanumeric_ratio,
    calculate_printable_ratio,
    clean_extracted_text,
    count_alphanumeric_characters,
    count_words,
    normalize_line_endings,
    normalize_unicode,
    normalize_whitespace,
    remove_control_characters,
    remove_null_bytes,
    truncate_text,
)

__all__ = [
    "build_download_filename",
    "calculate_alphanumeric_ratio",
    "calculate_printable_ratio",
    "calculate_sha256",
    "clean_extracted_text",
    "count_alphanumeric_characters",
    "count_words",
    "normalize_line_endings",
    "normalize_unicode",
    "normalize_whitespace",
    "output_stem",
    "read_binary_file",
    "remove_control_characters",
    "remove_null_bytes",
    "result_to_json_bytes",
    "result_to_text",
    "result_to_text_bytes",
    "sanitize_filename",
    "truncate_text",
]
