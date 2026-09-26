"""Wandaraya Component 4 — Language Detection Module public API."""

from __future__ import annotations

from app.onboarding.language_detection.cache import (
    BACKEND_DISABLED,
    BACKEND_MEMORY,
    BACKEND_REDIS,
    LanguageDetectionCache,
)
from app.onboarding.language_detection.detector import (
    CODE_CODE_MIXED,
    CODE_ENGLISH,
    CODE_NON_TEXT,
    CODE_SINGLISH,
    CODE_SINHALA,
    CODE_UNKNOWN,
    SAMPLE_INPUTS,
    SOURCE_CACHE,
    SOURCE_CHARACTER_HEURISTIC,
    SOURCE_FASTTEXT,
    SOURCE_RULES,
    LanguageDetectionError,
    LanguageDetector,
)
from app.onboarding.language_detection.fallback import CharacterBasedDetector
from app.onboarding.language_detection.fasttext_model import (
    FastTextModel,
    FastTextModelError,
)
from app.onboarding.language_detection.utils import (
    build_cache_key,
    clean_text,
    contains_latin,
    contains_only_emoji_or_symbols,
    contains_sinhala,
    get_script_mix,
    get_text_length,
    get_word_count,
    is_code_switched,
    load_config,
    parse_fasttext_label,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # Primary entry point
    "LanguageDetector",
    "LanguageDetectionError",
    # Model
    "FastTextModel",
    "FastTextModelError",
    # Fallback
    "CharacterBasedDetector",
    # Cache
    "LanguageDetectionCache",
    "BACKEND_REDIS",
    "BACKEND_MEMORY",
    "BACKEND_DISABLED",
    # Required utils
    "is_code_switched",
    "contains_sinhala",
    "contains_latin",
    "contains_only_emoji_or_symbols",
    "clean_text",
    "load_config",
    "get_text_length",
    # Supporting utils
    "get_script_mix",
    "get_word_count",
    "build_cache_key",
    "parse_fasttext_label",
    # Result codes
    "CODE_SINHALA",
    "CODE_ENGLISH",
    "CODE_SINGLISH",
    "CODE_CODE_MIXED",
    "CODE_NON_TEXT",
    "CODE_UNKNOWN",
    # Result sources
    "SOURCE_FASTTEXT",
    "SOURCE_CHARACTER_HEURISTIC",
    "SOURCE_CACHE",
    "SOURCE_RULES",
    # Demo data
    "SAMPLE_INPUTS",
]