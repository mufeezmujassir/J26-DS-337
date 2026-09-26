"""Helper functions for the Wandaraya language detection module.

Scope: detection only. Nothing here translates, rewrites, or resolves
code-switching; it only inspects text so the detector can label it.

The public helpers are the seven required by the module contract:

- :func:`is_code_switched`
- :func:`contains_sinhala`
- :func:`contains_latin`
- :func:`contains_only_emoji_or_symbols`
- :func:`clean_text`
- :func:`load_config`
- :func:`get_text_length`

The remaining helpers (script ranges, fastText label parsing, cache
keys) support those seven and the detector wiring.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

LOGGER = logging.getLogger(__name__)

LABEL_PREFIX = "__label__"

SINHALA_PATTERN = re.compile(r"[\u0D80-\u0DFF]")

LATIN_PATTERN = re.compile(
    r"[A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u024F]"
)

DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")

CJK_PATTERN = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")

CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04FF\u0500-\u052F]")

GREEK_PATTERN = re.compile(r"[\u0370-\u03FF]")

ARABIC_PATTERN = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")

TAMIL_PATTERN = re.compile(r"[\u0B80-\u0BFF]")

WORD_CATEGORIES = frozenset(
    {
        "Lu",
        "Ll",
        "Lt",
        "Lm",
        "Lo",
        "Mn",
        "Mc",
        "Me",
    }
)

WHITESPACE_PATTERN = re.compile(r"\s+", re.UNICODE)

KEYCAP_PATTERN = re.compile(r"[0-9#*]\ufe0f?\u20e3")

CURRENCY_SYMBOLS = frozenset({"$", "\u20a8", "\u20b9", "\u20bd", "\u20a9"})

SYMBOL_ONLY_CATEGORIES = frozenset(
    {
        "So",
        "Sk",
        "Sm",
        "Sc",
        "Pd",
        "Ps",
        "Pe",
        "Pi",
        "Pf",
        "Po",
        "Cf",
        "Mn",
        "Me",
        "Cc",
    }
)

SCRIPT_PATTERNS: Dict[str, re.Pattern[str]] = {
    "Sinhala": SINHALA_PATTERN,
    "Latin": LATIN_PATTERN,
    "Devanagari": DEVANAGARI_PATTERN,
    "CJK": CJK_PATTERN,
    "Cyrillic": CYRILLIC_PATTERN,
    "Greek": GREEK_PATTERN,
    "Arabic": ARABIC_PATTERN,
    "Tamil": TAMIL_PATTERN,
}

ISO3_TO_ISO1: Dict[str, str] = {
    "eng": "en",
    "sin": "si",
    "hin": "hi",
    "zho": "zh",
    "cmn": "zh",
    "yue": "zh",
    "wuu": "zh",
    "deu": "de",
    "ger": "de",
    "fra": "fr",
    "fre": "fr",
    "rus": "ru",
    "ita": "it",
    "spa": "es",
    "por": "pt",
    "nld": "nl",
    "jpn": "ja",
    "kor": "ko",
    "tha": "th",
    "tam": "ta",
    "tel": "te",
    "ben": "bn",
    "pan": "pa",
    "ind": "id",
    "msa": "ms",
    "tur": "tr",
    "ara": "ar",
    "fas": "fa",
    "ell": "el",
    "heb": "he",
    "ukr": "uk",
    "pol": "pl",
    "swe": "sv",
    "dan": "da",
    "nor": "no",
    "fin": "fi",
    "ces": "cs",
    "ron": "ro",
    "swa": "sw",
    "mya": "my",
    "khm": "km",
    "lao": "lo",
    "amh": "am",
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "model": {
        "repo_id": "facebook/fasttext-language-identification",
        "filename": "model.bin",
        "local_dir": "models/fasttext-language-identification",
        "local_path": None,
        "local_files_only": False,
        "top_k": 3,
    },
    "thresholds": {
        "standard_confidence": 0.70,
        "short_text_confidence": 0.50,
        "fallback_confidence": 0.50,
        "script_confidence": 0.95,
        "singlish_confidence": 0.60,
    },
    "languages": {
        "si": {"name": "Sinhala", "model_codes": ["si", "sin"]},
        "en": {"name": "English", "model_codes": ["en", "eng"]},
        "singlish": {"name": "Singlish", "model_codes": []},
        "code_mixed": {
            "name": "Code-Switched",
            "model_codes": [],
        },
        "hi": {"name": "Hindi", "model_codes": ["hi", "hin"]},
        "zh": {"name": "Chinese", "model_codes": ["zh", "zho", "cmn"]},
        "de": {"name": "German", "model_codes": ["de", "deu"]},
        "fr": {"name": "French", "model_codes": ["fr", "fra"]},
        "ru": {"name": "Russian", "model_codes": ["ru", "rus"]},
        "it": {"name": "Italian", "model_codes": ["it", "ita"]},
        "es": {"name": "Spanish", "model_codes": ["es", "spa"]},
    },
    "special_codes": {
        "non_text": {
            "name": "non-text",
            "model_codes": [],
        },
        "unknown": {
            "name": "unknown",
            "model_codes": [],
        },
    },
    "cache": {
        "enabled": True,
        "ttl_seconds": 86400,
        "redis_url": "redis://localhost:6379/0",
        "key_prefix": "langdetect",
        "socket_timeout_seconds": 1.0,
        "max_memory_entries": 10000,
    },
    "short_text": {
        "min_length": 2,
        "single_word_max_length": 5,
        "single_word_max_words": 1,
        "allow_emoji_gate": True,
    },
    "singlish": {
        "enabled": True,
        "min_tokens": 2,
        "min_markers": 1,
        "english_stopword_guard": True,
        "english_stopword_guard_count": 3,
        "lexicon": [],
    },
    "logging": {
        "level": "INFO",
        "log_predictions": True,
    },
}


def contains_sinhala(text: str) -> bool:
    """Return True when the text holds Sinhala Unicode (U+0D80-U+0DFF).

    Sinhala dependent vowel signs and the virama (U+0DCA) live in the
    same block, so a syllable-initial check is not required.
    """

    if not isinstance(text, str) or not text:
        return False

    return bool(SINHALA_PATTERN.search(text))


def contains_latin(text: str) -> bool:
    """Return True when the text holds Latin alphabet characters.

    Covers ASCII plus Latin-1 Supplement and Latin Extended-A/B, so
    accented Latin (``café``, ``müller``) still counts as Latin script.
    The multiplication and division signs in Latin-1 are excluded
    because they are symbols, not letters.
    """

    if not isinstance(text, str) or not text:
        return False

    return bool(LATIN_PATTERN.search(text))


def is_code_switched(text: str) -> bool:
    """Return True when Sinhala script and Latin script coexist.

    This is the module's code-switch signal. Segments are *not* split
    here; the Code-Switch Handler downstream owns that work.
    """

    if not isinstance(text, str) or not text:
        return False

    return contains_sinhala(text) and contains_latin(text)


def get_script_mix(text: str) -> List[str]:
    """Return the sorted set of scripts present in the text.

    Used for diagnostics and for widening the code-switch signal beyond
    the Sinhala+Latin contract when configured to do so.
    """

    if not isinstance(text, str) or not text:
        return []

    return sorted(
        name
        for name, pattern in SCRIPT_PATTERNS.items()
        if pattern.search(text)
    )


def contains_only_emoji_or_symbols(
    text: str,
) -> bool:
    """Return True when the text is only emoji, symbols, or punctuation.

    Digits and letters always make the answer False, so ``"5"`` and
    ``"ok"`` stay real text while ``"👍"``, ``"🔥🔥"`` and ``"!!!"``
    are treated as non-text. Keycap sequences such as ``"1️⃣"`` are
    normalised first because their base character is a digit.
    """

    if not isinstance(text, str):
        return False

    candidate = text.strip()

    if not candidate:
        return False

    candidate = KEYCAP_PATTERN.sub("\u20e3", candidate)

    if not candidate:
        return False

    return all(
        unicodedata.category(character) in SYMBOL_ONLY_CATEGORIES
        for character in candidate
    )


def clean_text(text: str) -> str:
    """Strip and NFC-normalise the text for stable detection.

    Only whitespace and Unicode composition are touched. The text is
    never transliterated, translated, or case-folded, because this
    module must not rewrite what the user typed.
    """

    if not isinstance(text, str):
        return ""

    normalised = unicodedata.normalize("NFC", text)

    normalised = normalised.replace("\u00a0", " ")

    return WHITESPACE_PATTERN.sub(" ", normalised).strip()


def get_text_length(text: str) -> int:
    """Return the effective text length, excluding whitespace."""

    if not isinstance(text, str):
        return 0

    return len(WHITESPACE_PATTERN.sub("", text))


def get_word_tokens(text: str) -> List[str]:
    """Split the text into word tokens.

    Characters are grouped by Unicode general category rather than with
    a ``\\w`` regular expression. ``\\w`` is based on ``str.isalnum()``,
    which excludes combining marks, so a regex tokeniser splits Sinhala
    and Devanagari words at every vowel sign and virama. Categories
    ``L*`` (letters) and ``M*`` (marks) are treated as word characters
    here, which keeps ``"මම කොළඹ යන්න ඕන"`` at four words instead of six.

    Args:
        text: Text to tokenise.

    Returns:
        The word tokens, in order. Combining marks stay attached to the
        letter they follow.
    """

    if not isinstance(text, str) or not text:
        return []

    tokens: List[str] = []
    current: List[str] = []

    for character in text:
        if unicodedata.category(character) in WORD_CATEGORIES:
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []

    if current:
        tokens.append("".join(current))

    return tokens


def get_word_count(text: str) -> int:
    """Return the number of word-like tokens in the text."""

    return len(get_word_tokens(text))


def is_short_text(
    text: str,
    min_length: int = 2,
    single_word_max_length: int = 5,
    single_word_max_words: int = 1,
) -> bool:
    """Return True when the text is too small to trust the model.

    Two cases are short: anything under ``min_length`` characters, and
    a single word under ``single_word_max_length`` characters.
    """

    if not isinstance(text, str):
        return False

    if not text:
        return True

    length = get_text_length(text)

    if length < min_length:
        return True

    word_count = get_word_count(text)

    return (
        word_count <= single_word_max_words
        and length < single_word_max_length
    )


def is_single_short_word(
    text: str,
    single_word_max_length: int = 5,
    single_word_max_words: int = 1,
) -> bool:
    """Return True for a one-or-fewer-word message under the length cap.

    This is the subset of short input that still warrants a prediction
    with the lowered confidence threshold.
    """

    if not isinstance(text, str) or not text:
        return False

    return (
        get_word_count(text) <= single_word_max_words
        and get_text_length(text) < single_word_max_length
    )


def is_probably_singlish(
    text: str,
    lexicon: Sequence[str],
    min_tokens: int = 2,
    min_markers: int = 1,
    stopwords: Sequence[str] = (),
    stopword_guard_count: int = 3,
) -> bool:
    """Return True when Latin text looks like Romanized Sinhala.

    fastText has no Singlish class, so the lexicon is the only signal.
    A hit needs at least ``min_markers`` markers and, unless the
    stopword guard suppresses it, a minimum number of tokens. The
    guard stops ordinary English that happens to contain a marker word
    from being relabelled.
    """

    if not isinstance(text, str) or not text:
        return False

    if not lexicon:
        return False

    tokens = [
        token.lower()
        for token in get_word_tokens(text)
    ]

    if len(tokens) < min_tokens:
        return False

    marker_set = {marker.lower() for marker in lexicon}

    markers = [
        token
        for token in tokens
        if token in marker_set
    ]

    if len(markers) < min_markers:
        return False

    if stopwords:
        stopword_set = {word.lower() for word in stopwords}

        guard_hits = sum(
            1
            for token in tokens
            if token in stopword_set
        )

        if guard_hits >= stopword_guard_count:
            return False

    return True


def find_singlish_markers(
    text: str,
    lexicon: Sequence[str],
) -> List[str]:
    """Return the Romanized-Sinhala markers present in the text."""

    if not isinstance(text, str) or not lexicon:
        return []

    marker_set = {marker.lower() for marker in lexicon}

    return [
        token
        for token in get_word_tokens(text.lower())
        if token in marker_set
    ]


def strip_fasttext_label(label: str) -> str:
    """Return the label body without the ``__label__`` prefix."""

    if not isinstance(label, str):
        return ""

    if label.startswith(LABEL_PREFIX):
        return label[len(LABEL_PREFIX) :].strip()

    return label.strip()


def parse_fasttext_label(
    label: str,
) -> Tuple[str, Optional[str]]:
    """Split a fastText label into its base code and script code.

    ``facebook/fasttext-language-identification`` is the lid218e model,
    whose labels are ``{iso639-3}_{script}``, for example
    ``__label__eng_Latn`` or ``__label__sin_Sinh``. The older lid.176
    models emit bare ISO 639-1 codes, so both shapes are accepted.

    Returns a ``(base_code, script_code)`` tuple where ``base_code`` is
    downgraded to ISO 639-1 when a mapping exists.
    """

    body = strip_fasttext_label(label)

    if not body:
        return "", None

    parts = body.split("_")

    base = parts[0].lower()
    script = parts[1].upper() if len(parts) > 1 and parts[1] else None

    base = ISO3_TO_ISO1.get(base, base)

    return base, script


def build_cache_key(text: str, prefix: str = "langdetect") -> str:
    """Return the cache key ``"langdetect:{hash_of_text}"``.

    The text is hashed rather than embedded so that long messages and
    control characters cannot corrupt a key.
    """

    normalised = clean_text(text).lower()

    digest = hashlib.sha256(
        normalised.encode("utf-8")
    ).hexdigest()

    return f"{prefix}:{digest}"


def load_config(config_path: str) -> Dict[str, Any]:
    """Load the YAML configuration and merge it over the defaults.

    Missing keys fall back to :data:`DEFAULT_CONFIG` so a partial
    ``config.yaml`` never breaks detection. A missing or malformed file
    is a real error and raises, because the config is a local file that
    must always be present.
    """

    path = Path(config_path).expanduser()

    if not path.is_file():
        raise FileNotFoundError(
            f"Language detection config not found: {path}"
        )

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except yaml.YAMLError as error:
        raise ValueError(
            f"Language detection config is not valid YAML: {path} "
            f"({error})"
        ) from error

    if raw is None:
        raw = {}

    if not isinstance(raw, dict):
        raise ValueError(
            f"Language detection config must be a YAML mapping, got "
            f"{type(raw).__name__}: {path}"
        )

    return deep_merge(DEFAULT_CONFIG, raw)


def deep_merge(
    base: Dict[str, Any],
    override: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a new dict with ``override`` recursively merged into ``base``.

    Neither input is mutated, so the module-level defaults stay clean
    between detector instances.
    """

    merged = copy.deepcopy(base)

    for key, value in (override or {}).items():
        current = merged.get(key)

        if (
            isinstance(current, dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = copy.deepcopy(value)

    return merged


def resolve_project_root() -> Path:
    """Return the ``wandaraya-backend`` root directory.

    ``<root>/app/onboarding/language_detection/utils.py`` is four levels
    deep, so ``parents[3]`` is the backend root.
    """

    return Path(__file__).resolve().parents[3]
