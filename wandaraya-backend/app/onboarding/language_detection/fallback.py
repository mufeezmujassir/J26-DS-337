"""Character-based heuristic language detection."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.onboarding.language_detection.utils import (
    ARABIC_PATTERN,
    CJK_PATTERN,
    CYRILLIC_PATTERN,
    DEVANAGARI_PATTERN,
    GREEK_PATTERN,
    TAMIL_PATTERN,
    clean_text,
    contains_latin,
    contains_only_emoji_or_symbols,
    contains_sinhala,
    get_script_mix,
    get_text_length,
    is_code_switched,
)

LOGGER = logging.getLogger(__name__)

SOURCE_CHARACTER_HEURISTIC = "character_heuristic"

LANGUAGE_SINHALA = "Sinhala"
LANGUAGE_ENGLISH = "English"
LANGUAGE_CODE_SWITCHED = "Code-Switched"
LANGUAGE_NON_TEXT = "non-text"
LANGUAGE_UNKNOWN = "unknown"

CODE_SINHALA = "si"
CODE_ENGLISH = "en"
CODE_CODE_MIXED = "code_mixed"
CODE_NON_TEXT = "non_text"
CODE_UNKNOWN = "unknown"

SCRIPT_RULE_ORDER = (
    ("Devanagari", "Hindi", "hi"),
    ("CJK", "Chinese", "zh"),
    ("Cyrillic", "Russian", "ru"),
    ("Tamil", "Tamil", "ta"),
    ("Greek", "Greek", "el"),
    ("Arabic", "Arabic", "ar"),
)

SCRIPT_PATTERNS_BY_NAME = {
    "Devanagari": DEVANAGARI_PATTERN,
    "CJK": CJK_PATTERN,
    "Cyrillic": CYRILLIC_PATTERN,
    "Tamil": TAMIL_PATTERN,
    "Greek": GREEK_PATTERN,
    "Arabic": ARABIC_PATTERN,
}


class CharacterBasedDetector:
    """Deterministic script-based language detector.

    No model, no network, no disk access. Used when the fastText model
    is unavailable or scores below the fallback threshold.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Create the detector. Reads only ``thresholds.script_confidence``."""

        self._config = config or {}

        thresholds = self._config.get("thresholds") or {}

        self._script_confidence = float(
            thresholds.get("script_confidence", 0.95)
        )

    def detect(self, text: str) -> Dict[str, Any]:
        """Detect the language of the text from its character ranges."""

        if not isinstance(text, str):
            LOGGER.warning(
                "Character fallback received non-string input of type %s",
                type(text).__name__,
            )

            return self._build_result(
                language=LANGUAGE_UNKNOWN,
                code=CODE_UNKNOWN,
                confidence=0.0,
                is_code_switched=False,
                short_text=True,
                non_text=False,
            )

        cleaned = clean_text(text)

        if not cleaned:
            return self._build_result(
                language=LANGUAGE_UNKNOWN,
                code=CODE_UNKNOWN,
                confidence=0.0,
                is_code_switched=False,
                short_text=True,
                non_text=False,
            )

        if contains_only_emoji_or_symbols(cleaned):
            return self._build_result(
                language=LANGUAGE_NON_TEXT,
                code=CODE_NON_TEXT,
                confidence=1.0,
                is_code_switched=False,
                short_text=False,
                non_text=True,
            )

        has_sinhala = contains_sinhala(cleaned)
        has_latin = contains_latin(cleaned)

        if has_sinhala and has_latin:
            return self._build_result(
                language=LANGUAGE_CODE_SWITCHED,
                code=CODE_CODE_MIXED,
                confidence=self._script_confidence,
                is_code_switched=True,
                short_text=False,
                non_text=False,
            )

        if has_sinhala:
            return self._build_result(
                language=LANGUAGE_SINHALA,
                code=CODE_SINHALA,
                confidence=self._script_confidence,
                is_code_switched=False,
                short_text=False,
                non_text=False,
            )

        if has_latin:
            return self._build_result(
                language=LANGUAGE_ENGLISH,
                code=CODE_ENGLISH,
                confidence=self._script_confidence,
                is_code_switched=False,
                short_text=False,
                non_text=False,
            )

        return self._detect_other_script(cleaned)

    def get_scripts(self, text: str) -> list:
        """Return the scripts present in the text, sorted by name."""

        return get_script_mix(text)

    def is_code_switched(self, text: str) -> bool:
        """Return True when Sinhala and Latin script coexist."""

        return is_code_switched(text)

    def _detect_other_script(self, text: str) -> Dict[str, Any]:
        """Map a non-Sinhala, non-Latin script to its language."""

        for script_name, language, code in SCRIPT_RULE_ORDER:
            pattern = SCRIPT_PATTERNS_BY_NAME[script_name]

            if pattern.search(text):
                return self._build_result(
                    language=language,
                    code=code,
                    confidence=self._script_confidence,
                    is_code_switched=False,
                    short_text=False,
                    non_text=False,
                )

        LOGGER.debug(
            "Character fallback found no mapped script in %r, "
            "scripts=%s, length=%d",
            text[:40],
            get_script_mix(text),
            get_text_length(text),
        )

        return self._build_result(
            language=LANGUAGE_UNKNOWN,
            code=CODE_UNKNOWN,
            confidence=0.0,
            is_code_switched=False,
            short_text=False,
            non_text=False,
        )

    def _build_result(
        self,
        language: str,
        code: str,
        confidence: float,
        is_code_switched: bool,
        short_text: bool,
        non_text: bool,
    ) -> Dict[str, Any]:
        """Assemble a detection result in the canonical shape."""

        return {
            "language": language,
            "language_code": code,
            "confidence": round(float(confidence), 4),
            "is_code_switched": is_code_switched,
            "low_confidence": False,
            "short_text": short_text,
            "non_text": non_text,
            "fallback_used": True,
            "raw_label": None,
            "source": SOURCE_CHARACTER_HEURISTIC,
        }