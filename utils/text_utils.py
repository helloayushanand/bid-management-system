"""Text cleaning and formatting utilities."""

from __future__ import annotations

import re
import unicodedata


_CONTROL_CHARACTER_PATTERN = re.compile(
    r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]"
)
_HORIZONTAL_WHITESPACE_PATTERN = re.compile(r"[^\S\r\n]+")
_EXCESSIVE_BLANK_LINES_PATTERN = re.compile(r"\n{3,}")
_WORD_PATTERN = re.compile(r"\b[\w'-]+\b", flags=re.UNICODE)


def normalize_unicode(text: str) -> str:
    """
    Normalize Unicode text using NFKC normalization.

    This standardizes visually equivalent characters and improves
    downstream comparisons without converting the text to ASCII.
    """

    if not text:
        return ""

    return unicodedata.normalize("NFKC", text)


def remove_control_characters(text: str) -> str:
    """Remove non-printable control characters while preserving newlines."""

    if not text:
        return ""

    return _CONTROL_CHARACTER_PATTERN.sub("", text)


def normalize_line_endings(text: str) -> str:
    """Convert Windows and legacy line endings to newline characters."""

    if not text:
        return ""

    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_whitespace(text: str) -> str:
    """
    Normalize unnecessary whitespace while preserving page structure.

    The function:
    - converts tabs and repeated horizontal spaces to one space;
    - removes spaces at the beginning and end of lines;
    - limits consecutive blank lines to two.
    """

    if not text:
        return ""

    normalized_lines: list[str] = []

    for line in text.split("\n"):
        line = _HORIZONTAL_WHITESPACE_PATTERN.sub(" ", line)
        normalized_lines.append(line.strip())

    normalized = "\n".join(normalized_lines)
    normalized = _EXCESSIVE_BLANK_LINES_PATTERN.sub("\n\n", normalized)

    return normalized.strip()


def remove_null_bytes(text: str) -> str:
    """Remove null bytes that can break JSON and text processing."""

    if not text:
        return ""

    return text.replace("\x00", "")


def clean_extracted_text(text: str | None) -> str:
    """
    Apply safe cleanup to text extracted from a PDF page.

    The function deliberately preserves line breaks because they may
    represent headings, paragraphs, lists, or table-like structures.
    """

    if not text:
        return ""

    cleaned = normalize_line_endings(text)
    cleaned = remove_null_bytes(cleaned)
    cleaned = remove_control_characters(cleaned)
    cleaned = normalize_unicode(cleaned)
    cleaned = normalize_whitespace(cleaned)

    return cleaned


def count_words(text: str | None) -> int:
    """Count word-like tokens in extracted text."""

    if not text:
        return 0

    return len(_WORD_PATTERN.findall(text))


def count_alphanumeric_characters(text: str | None) -> int:
    """Count letters and digits in text."""

    if not text:
        return 0

    return sum(character.isalnum() for character in text)


def calculate_alphanumeric_ratio(text: str | None) -> float:
    """
    Return the proportion of non-whitespace characters that are alphanumeric.

    A low value can indicate corrupted extraction, excessive symbols,
    or a page dominated by non-text content.
    """

    if not text:
        return 0.0

    non_whitespace_characters = [
        character for character in text if not character.isspace()
    ]

    if not non_whitespace_characters:
        return 0.0

    alphanumeric_count = sum(
        character.isalnum()
        for character in non_whitespace_characters
    )

    return alphanumeric_count / len(non_whitespace_characters)


def calculate_printable_ratio(text: str | None) -> float:
    """Return the proportion of characters that are printable or whitespace."""

    if not text:
        return 0.0

    acceptable_count = sum(
        character.isprintable() or character in "\n\r\t"
        for character in text
    )

    return acceptable_count / len(text)


def truncate_text(
    text: str,
    maximum_characters: int,
    suffix: str = "\n\n[Preview truncated]",
) -> str:
    """Truncate text for UI preview without modifying stored output."""

    if maximum_characters < 0:
        raise ValueError("maximum_characters must be zero or greater.")

    if len(text) <= maximum_characters:
        return text

    if maximum_characters == 0:
        return suffix.strip()

    return f"{text[:maximum_characters].rstrip()}{suffix}"
