"""Heuristics for evaluating extracted PDF page text."""

from __future__ import annotations

from dataclasses import dataclass, field

from utils.text_utils import (
    calculate_alphanumeric_ratio,
    clean_extracted_text,
)


@dataclass(frozen=True)
class TextQualityResult:
    """Result of evaluating text extracted from one PDF page."""

    score: float
    is_usable: bool
    requires_ocr: bool
    needs_review: bool
    reasons: list[str] = field(default_factory=list)


def calculate_printable_ratio(text: str) -> float:
    """Return the ratio of printable characters in the supplied text."""

    if not text:
        return 0.0

    printable_count = sum(
        character.isprintable() or character in "\n\r\t"
        for character in text
    )

    return printable_count / len(text)


def calculate_replacement_character_ratio(text: str) -> float:
    """Return the ratio of Unicode replacement characters."""

    if not text:
        return 0.0

    replacement_count = text.count("\ufffd")

    return replacement_count / len(text)


def calculate_letter_count(text: str) -> int:
    """Return the number of alphabetic characters in the text."""

    return sum(character.isalpha() for character in text)


def clamp_score(value: float) -> float:
    """Clamp a numeric value to the inclusive range zero to one."""

    return max(0.0, min(1.0, value))


def evaluate_text_quality(
    text: str | None,
    *,
    minimum_characters: int = 80,
    minimum_letters: int = 30,
    minimum_alphanumeric_ratio: float = 0.40,
    minimum_printable_ratio: float = 0.90,
    maximum_replacement_ratio: float = 0.02,
) -> TextQualityResult:
    """
    Evaluate whether extracted page text is adequate for processing.

    These checks are configurable heuristics. They indicate whether the
    native PDF text is likely to be usable or whether OCR should be tried.
    """

    cleaned_text = clean_extracted_text(text or "")

    character_count = len(cleaned_text)
    letter_count = calculate_letter_count(cleaned_text)
    alphanumeric_ratio = calculate_alphanumeric_ratio(cleaned_text)
    printable_ratio = calculate_printable_ratio(cleaned_text)
    replacement_ratio = calculate_replacement_character_ratio(cleaned_text)

    reasons: list[str] = []

    if character_count == 0:
        reasons.append("No text was extracted from the page.")

    elif character_count < minimum_characters:
        reasons.append(
            "Extracted text contains fewer than "
            f"{minimum_characters} characters."
        )

    if character_count > 0 and letter_count < minimum_letters:
        reasons.append(
            "Extracted text contains fewer than "
            f"{minimum_letters} alphabetic characters."
        )

    if (
        character_count > 0
        and alphanumeric_ratio < minimum_alphanumeric_ratio
    ):
        reasons.append(
            "Alphanumeric character ratio is below "
            f"{minimum_alphanumeric_ratio:.2f}."
        )

    if (
        character_count > 0
        and printable_ratio < minimum_printable_ratio
    ):
        reasons.append(
            "Printable character ratio is below "
            f"{minimum_printable_ratio:.2f}."
        )

    if replacement_ratio > maximum_replacement_ratio:
        reasons.append(
            "Unicode replacement character ratio exceeds "
            f"{maximum_replacement_ratio:.2f}."
        )

    length_score = min(
        character_count / max(minimum_characters, 1),
        1.0,
    )

    letter_score = min(
        letter_count / max(minimum_letters, 1),
        1.0,
    )

    score = clamp_score(
        (0.30 * length_score)
        + (0.20 * letter_score)
        + (0.25 * alphanumeric_ratio)
        + (0.20 * printable_ratio)
        + (0.05 * (1.0 - replacement_ratio))
    )

    is_usable = (
        character_count >= minimum_characters
        and letter_count >= minimum_letters
        and alphanumeric_ratio >= minimum_alphanumeric_ratio
        and printable_ratio >= minimum_printable_ratio
        and replacement_ratio <= maximum_replacement_ratio
    )

    return TextQualityResult(
        score=round(score, 4),
        is_usable=is_usable,
        requires_ocr=not is_usable,
        needs_review=not is_usable,
        reasons=reasons,
    )


def should_run_ocr(
    text: str | None,
    *,
    minimum_characters: int = 80,
) -> bool:
    """Return whether a page should be sent to the OCR extractor."""

    result = evaluate_text_quality(
        text,
        minimum_characters=minimum_characters,
    )

    return result.requires_ocr