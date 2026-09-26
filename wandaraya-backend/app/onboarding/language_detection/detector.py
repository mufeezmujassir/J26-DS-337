"""Language detection for the Wandaraya group chat."""

from __future__ import annotations

import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.onboarding.language_detection.cache import LanguageDetectionCache
from app.onboarding.language_detection.fallback import CharacterBasedDetector
from app.onboarding.language_detection.fasttext_model import FastTextModel
from app.onboarding.language_detection.utils import (
    clean_text,
    contains_latin,
    contains_only_emoji_or_symbols,
    contains_sinhala,
    find_singlish_markers,
    get_text_length,
    is_probably_singlish,
    is_single_short_word,
    load_config,
    parse_fasttext_label,
)

LOGGER = logging.getLogger(__name__)

PACKAGE_LOGGER_NAME = "app.onboarding.language_detection"
MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = MODULE_DIR / "config.yaml"

SOURCE_FASTTEXT = "fasttext"
SOURCE_CHARACTER_HEURISTIC = "character_heuristic"
SOURCE_CACHE = "cache"
SOURCE_RULES = "rules"

LANGUAGE_SINHALA = "Sinhala"
LANGUAGE_ENGLISH = "English"
LANGUAGE_SINGLISH = "Singlish"
LANGUAGE_CODE_SWITCHED = "Code-Switched"
LANGUAGE_NON_TEXT = "non-text"
LANGUAGE_UNKNOWN = "unknown"

CODE_SINHALA = "si"
CODE_ENGLISH = "en"
CODE_SINGLISH = "singlish"
CODE_CODE_MIXED = "code_mixed"
CODE_NON_TEXT = "non_text"
CODE_UNKNOWN = "unknown"

LOCAL_LANGUAGE_CODES = frozenset(
    {CODE_SINHALA, CODE_ENGLISH, CODE_SINGLISH, CODE_CODE_MIXED}
)


class LanguageDetectionError(RuntimeError):
    """Raised for unrecoverable language detection setup failures."""


class LanguageDetector:
    """Detects the language of Wandaraya chat messages."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        use_cache: Optional[bool] = None,
        auto_load_model: bool = True,
        model: Optional[FastTextModel] = None,
    ) -> None:
        """Create the detector and load its dependencies.

        A missing fastText model is not fatal; the detector logs a
        warning and falls back to character heuristics.
        """

        if config is not None:
            self.config = config
        else:
            self.config = self._load_config_or_raise(config_path)

        self._configure_logging()

        self._thresholds = self.config.get("thresholds") or {}
        self._short_text_config = self.config.get("short_text") or {}
        self._singlish_config = self.config.get("singlish") or {}
        self._model_config = self.config.get("model") or {}

        self._language_names = self._build_language_names()
        self._model_code_map = self._build_model_code_map()

        self._standard_threshold = float(
            self._thresholds.get("standard_confidence", 0.70)
        )
        self._short_threshold = float(
            self._thresholds.get("short_text_confidence", 0.50)
        )
        self._fallback_threshold = float(
            self._thresholds.get("fallback_confidence", 0.50)
        )
        self._script_confidence = float(
            self._thresholds.get("script_confidence", 0.95)
        )
        self._singlish_confidence = float(
            self._thresholds.get("singlish_confidence", 0.60)
        )

        self._min_length = int(
            self._short_text_config.get("min_length", 2)
        )
        self._single_word_max_length = int(
            self._short_text_config.get("single_word_max_length", 5)
        )
        self._single_word_max_words = int(
            self._short_text_config.get("single_word_max_words", 1)
        )
        self._allow_emoji_gate = bool(
            self._short_text_config.get("allow_emoji_gate", True)
        )

        self._log_predictions = bool(
            (self.config.get("logging") or {}).get("log_predictions", True)
        )

        self._singlish_enabled = bool(
            self._singlish_config.get("enabled", True)
        )
        self._singlish_lexicon = self._string_list(
            self._singlish_config.get("lexicon"),
            "singlish.lexicon",
        )
        self._singlish_min_tokens = int(
            self._singlish_config.get("min_tokens", 2)
        )
        self._singlish_min_markers = int(
            self._singlish_config.get("min_markers", 1)
        )
        self._english_stopwords = self._string_list(
            self._singlish_config.get("english_stopwords"),
            "singlish.english_stopwords",
        )
        self._stopword_guard_enabled = bool(
            self._singlish_config.get("english_stopword_guard", True)
        )
        self._stopword_guard_count = int(
            self._singlish_config.get("english_stopword_guard_count", 3)
        )

        self._fallback = CharacterBasedDetector(self.config)
        self._cache = self._build_cache(use_cache)
        self._model = model

        self._detections = 0
        self._cache_hits = 0
        self._fallback_uses = 0
        self._non_text_inputs = 0
        self._short_text_inputs = 0
        self._invalid_inputs = 0
        self._started_at = time.time()

        if model is not None:
            LOGGER.info(
                "Language detector initialised with an injected model "
                "(loaded=%s)",
                model.is_loaded,
            )
        elif auto_load_model:
            self.load_model()

    def detect(self, text: str) -> Dict[str, Any]:
        """Detect the language of a single message.

        Non-string input is reported as ``unknown`` rather than raising,
        because a malformed payload must not break a group chat.
        """

        if not isinstance(text, str):
            self._invalid_inputs += 1
            self._detections += 1

            LOGGER.warning(
                "Language detection received non-string input of type %s",
                type(text).__name__,
            )

            result = self._finalise(
                self._build_result(
                    language=LANGUAGE_UNKNOWN,
                    code=CODE_UNKNOWN,
                    confidence=0.0,
                    is_code_switched=False,
                    short_text=True,
                    non_text=False,
                    source=SOURCE_RULES,
                ),
                self._short_threshold,
            )
            result["error"] = f"Expected str, got {type(text).__name__}"

            return result

        cleaned = clean_text(text)
        result = self._detect_cleaned(text, cleaned)

        self._detections += 1

        if result["non_text"]:
            self._non_text_inputs += 1
        elif result["short_text"]:
            self._short_text_inputs += 1

        if result["fallback_used"]:
            self._fallback_uses += 1

        self._log_prediction(text, result)

        return result

    def detect_batch(
        self, texts: List[str]
    ) -> List[Dict[str, Any]]:
        """Detect several messages, preserving order."""

        if texts is None:
            LOGGER.warning("detect_batch received None instead of a list")
            return []

        if isinstance(texts, str):
            LOGGER.warning(
                "detect_batch received a bare string, treating it as a "
                "single-item batch"
            )
            return [self.detect(texts)]

        try:
            items = list(texts)
        except TypeError:
            LOGGER.warning(
                "detect_batch received a non-iterable of type %s",
                type(texts).__name__,
            )
            return []

        return [self.detect(item) for item in items]

    def get_supported_languages(
        self, include_special: bool = False
    ) -> List[str]:
        """Return the language codes this detector can emit."""

        codes = list((self.config.get("languages") or {}).keys())

        if include_special:
            special = self.config.get("special_codes") or {}
            codes.extend(special.keys())

        return codes

    def get_language_info(
        self, include_special: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """Return the full code-to-name mapping for routing tables."""

        info: Dict[str, Dict[str, Any]] = {
            code: {"name": name}
            for code, name in self._language_names.items()
        }

        if include_special:
            special = self.config.get("special_codes") or {}
            for code, entry in special.items():
                info[code] = {"name": entry.get("name", code)}

        return info

    def evaluate(
        self, test_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Score the detector against a labelled set.

        Each sample needs ``text`` and either ``language_code`` or
        ``language``. Raises :class:`LanguageDetectionError` when no
        usable samples remain.
        """

        if not test_data:
            raise LanguageDetectionError(
                "evaluate() requires a non-empty list of labelled samples."
            )

        expected: List[str] = []
        predicted: List[str] = []
        samples: List[Dict[str, str]] = []
        skipped = 0

        for index, sample in enumerate(test_data):
            if not isinstance(sample, dict):
                LOGGER.warning(
                    "Skipping test sample %d: expected dict, got %s",
                    index,
                    type(sample).__name__,
                )
                skipped += 1
                continue

            text = sample.get("text")
            label = sample.get("language_code") or sample.get("language")

            if not isinstance(text, str) or not label:
                LOGGER.warning(
                    "Skipping test sample %d: missing text or label",
                    index,
                )
                skipped += 1
                continue

            result = self.detect(text)

            expected.append(str(label))
            predicted.append(result["language_code"])
            samples.append(
                {
                    "text": text,
                    "expected": str(label),
                    "predicted": result["language_code"],
                    "confidence": result["confidence"],
                }
            )

        if not expected:
            raise LanguageDetectionError(
                "evaluate() found no usable labelled samples in the "
                "provided test data."
            )

        report = self._classification_report(expected, predicted)

        if report is not None:
            metrics = self._metrics_with_sklearn(expected, predicted)
        else:
            metrics = self._metrics_manual(expected, predicted)

        misclassified = [
            sample
            for sample in samples
            if sample["expected"] != sample["predicted"]
        ]

        metrics.update(
            {
                "total_samples": len(test_data),
                "evaluated_samples": len(expected),
                "skipped_samples": skipped,
                "accuracy": round(metrics["accuracy"], 4),
                "macro_f1": round(metrics["macro_f1"], 4),
                "weighted_f1": round(metrics["weighted_f1"], 4),
                "micro_f1": round(metrics["micro_f1"], 4),
                "correct": len(expected) - len(misclassified),
                "misclassified_count": len(misclassified),
                "misclassified": misclassified,
                "confusion": self._top_confusions(expected, predicted),
                "sklearn_report": report,
            }
        )

        LOGGER.info(
            "Language detection evaluation: %d/%d correct, accuracy=%.4f, "
            "macro_f1=%.4f",
            metrics["correct"],
            metrics["evaluated_samples"],
            metrics["accuracy"],
            metrics["macro_f1"],
        )

        return metrics

    def load_model(self) -> bool:
        """Load the fastText model. Returns True when ready."""

        if self._model is None:
            self._model = FastTextModel(
                repo_id=self._model_config.get(
                    "repo_id", "facebook/fasttext-language-identification"
                ),
                filename=self._model_config.get("filename", "model.bin"),
                local_dir=self._model_config.get(
                    "local_dir",
                    "models/fasttext-language-identification",
                ),
                local_path=self._model_config.get("local_path"),
                local_files_only=bool(
                    self._model_config.get("local_files_only", False)
                ),
                auto_load=True,
            )

        if self._model.is_loaded:
            return True

        loaded = self._model.try_load()

        if loaded:
            LOGGER.info(
                "Language detector using fastText model from %s",
                self._model.model_path,
            )
        else:
            LOGGER.warning(
                "Language detector running without fastText; all "
                "detection will use character heuristics.",
            )

        return loaded

    def close(self) -> None:
        """Release the model and cache resources."""

        if self._model is not None:
            self._model.unload()

        self._cache.close()

    def get_stats(self) -> Dict[str, Any]:
        """Return runtime counters and model/cache state."""

        return {
            "detections": self._detections,
            "cache_hits": self._cache_hits,
            "fallback_uses": self._fallback_uses,
            "non_text_inputs": self._non_text_inputs,
            "short_text_inputs": self._short_text_inputs,
            "invalid_inputs": self._invalid_inputs,
            "fallback_rate": (
                round(self._fallback_uses / self._detections, 4)
                if self._detections
                else 0.0
            ),
            "uptime_seconds": round(time.time() - self._started_at, 3),
            "model_loaded": bool(
                self._model is not None and self._model.is_loaded
            ),
            "model_source": (
                self._model.source if self._model is not None else None
            ),
            "model_path": (
                str(self._model.model_path)
                if self._model is not None and self._model.model_path
                else None
            ),
            "model_error": (
                self._model.load_error
                if self._model is not None
                else None
            ),
            "cache": self._cache.get_stats(),
            "thresholds": {
                "standard_confidence": self._standard_threshold,
                "short_text_confidence": self._short_threshold,
                "fallback_confidence": self._fallback_threshold,
            },
        }

    def _detect_cleaned(
        self, raw_text: str, cleaned: str
    ) -> Dict[str, Any]:
        """Run the detection pipeline on normalised text."""

        if not cleaned:
            return self._finalise(
                self._build_result(
                    language=LANGUAGE_UNKNOWN,
                    code=CODE_UNKNOWN,
                    confidence=0.0,
                    is_code_switched=False,
                    short_text=True,
                    non_text=False,
                    source=SOURCE_RULES,
                ),
                self._short_threshold,
            )

        if self._allow_emoji_gate and contains_only_emoji_or_symbols(
            cleaned
        ):
            return self._finalise(
                self._build_result(
                    language=LANGUAGE_NON_TEXT,
                    code=CODE_NON_TEXT,
                    confidence=1.0,
                    is_code_switched=False,
                    short_text=False,
                    non_text=True,
                    source=SOURCE_RULES,
                ),
                self._standard_threshold,
            )

        if get_text_length(cleaned) < self._min_length:
            return self._finalise(
                self._build_result(
                    language=LANGUAGE_UNKNOWN,
                    code=CODE_UNKNOWN,
                    confidence=0.0,
                    is_code_switched=False,
                    short_text=True,
                    non_text=False,
                    source=SOURCE_RULES,
                ),
                self._short_threshold,
            )

        cached = self._cache.get(cleaned)

        if cached is not None:
            self._cache_hits += 1

            return self._build_result(
                language=cached.get("language", LANGUAGE_UNKNOWN),
                code=cached.get("language_code", CODE_UNKNOWN),
                confidence=float(cached.get("confidence", 0.0) or 0.0),
                is_code_switched=bool(
                    cached.get("is_code_switched", False)
                ),
                short_text=bool(cached.get("short_text", False)),
                non_text=bool(cached.get("non_text", False)),
                fallback_used=bool(cached.get("fallback_used", False)),
                raw_label=cached.get("raw_label"),
                source=SOURCE_CACHE,
            )

        short_word = is_single_short_word(
            cleaned,
            single_word_max_length=self._single_word_max_length,
            single_word_max_words=self._single_word_max_words,
        )

        threshold = (
            self._short_threshold
            if short_word
            else self._standard_threshold
        )

        label, confidence = self._predict(cleaned)

        result = self._resolve_language(
            cleaned=cleaned,
            label=label,
            confidence=confidence,
            short_text=short_word,
            threshold=threshold,
        )

        self._cache.set(cleaned, result)

        return result

    def _predict(self, cleaned: str) -> tuple:
        """Run the model, returning ``(label, confidence)``."""

        if self._model is None or not self._model.is_loaded:
            return None, 0.0

        try:
            return self._model.predict(cleaned)
        except Exception as error:  # noqa: BLE001
            LOGGER.warning(
                "fastText prediction raised for text of length %d: %s",
                len(cleaned),
                error,
            )
            return None, 0.0

    def _resolve_language(
        self,
        cleaned: str,
        label: Optional[str],
        confidence: float,
        short_text: bool,
        threshold: float,
    ) -> Dict[str, Any]:
        """Turn a model prediction into the final labelled result.

        Priority: code-mixed script → Sinhala script → unsupported
        model label → usable model label → Singlish lexicon → character
        fallback.
        """

        has_sinhala = contains_sinhala(cleaned)
        has_latin = contains_latin(cleaned)

        model_code = self._map_model_label(label)

        model_confident = (
            label is not None
            and confidence >= self._fallback_threshold
        )
        model_usable = model_confident and model_code is not None
        model_agrees = (
            model_usable and model_code in LOCAL_LANGUAGE_CODES
        )

        if has_sinhala and has_latin:
            result = self._build_result(
                language=self._language_name(CODE_CODE_MIXED),
                code=CODE_CODE_MIXED,
                confidence=(
                    confidence if model_agrees else self._script_confidence
                ),
                is_code_switched=True,
                short_text=short_text,
                non_text=False,
                fallback_used=not model_agrees,
                raw_label=label,
                source=(
                    SOURCE_FASTTEXT
                    if model_agrees
                    else SOURCE_CHARACTER_HEURISTIC
                ),
            )
            return self._finalise(result, threshold)

        if has_sinhala:
            result = self._build_result(
                language=self._language_name(CODE_SINHALA),
                code=CODE_SINHALA,
                confidence=(
                    confidence
                    if model_usable and model_code == CODE_SINHALA
                    else self._script_confidence
                ),
                is_code_switched=False,
                short_text=short_text,
                non_text=False,
                fallback_used=not (
                    model_usable and model_code == CODE_SINHALA
                ),
                raw_label=label,
                source=(
                    SOURCE_FASTTEXT
                    if model_usable and model_code == CODE_SINHALA
                    else SOURCE_CHARACTER_HEURISTIC
                ),
            )
            return self._finalise(result, threshold)

        singlish_markers = self._singlish_markers(cleaned)
        singlish_hit = bool(singlish_markers)

        if model_confident and model_code is None:
            LOGGER.info(
                "Text in %s (%s) is not a supported language, reporting "
                "unknown rather than guessing",
                label,
                cleaned[:40],
            )

            result = self._build_result(
                language=LANGUAGE_UNKNOWN,
                code=CODE_UNKNOWN,
                confidence=confidence,
                is_code_switched=False,
                short_text=short_text,
                non_text=False,
                fallback_used=False,
                raw_label=label,
                source=SOURCE_FASTTEXT,
            )
            return self._finalise(result, threshold)

        if model_usable and model_code not in (CODE_SINHALA,):
            code = (
                CODE_SINGLISH
                if model_code == CODE_ENGLISH and singlish_hit
                else model_code
            )

            result = self._build_result(
                language=self._language_name(code),
                code=code,
                confidence=confidence,
                is_code_switched=False,
                short_text=short_text,
                non_text=False,
                fallback_used=False,
                raw_label=label,
                source=SOURCE_FASTTEXT,
            )
            return self._finalise(result, threshold)

        if singlish_hit:
            result = self._build_result(
                language=self._language_name(CODE_SINGLISH),
                code=CODE_SINGLISH,
                confidence=(
                    confidence
                    if model_code == CODE_ENGLISH and confidence > 0
                    else self._singlish_confidence
                ),
                is_code_switched=False,
                short_text=short_text,
                non_text=False,
                fallback_used=True,
                raw_label=label,
                source=SOURCE_CHARACTER_HEURISTIC,
            )
            return self._finalise(result, threshold)

        fallback_result = self._fallback.detect(cleaned)

        result = self._build_result(
            language=fallback_result["language"],
            code=fallback_result["language_code"],
            confidence=float(fallback_result["confidence"]),
            is_code_switched=bool(fallback_result["is_code_switched"]),
            short_text=short_text,
            non_text=bool(fallback_result["non_text"]),
            fallback_used=True,
            raw_label=label,
            source=SOURCE_CHARACTER_HEURISTIC,
        )

        return self._finalise(result, threshold)

    def _finalise(
        self, result: Dict[str, Any], threshold: float
    ) -> Dict[str, Any]:
        """Apply the confidence threshold to a built result."""

        result["low_confidence"] = result["confidence"] < threshold
        return result

    def _singlish_markers(self, cleaned: str) -> List[str]:
        """Return Romanized-Sinhala markers found in the text."""

        if not self._singlish_enabled or not self._singlish_lexicon:
            return []

        stopwords = (
            self._english_stopwords
            if self._stopword_guard_enabled
            else []
        )

        matched = is_probably_singlish(
            cleaned,
            lexicon=self._singlish_lexicon,
            min_tokens=self._singlish_min_tokens,
            min_markers=self._singlish_min_markers,
            stopwords=stopwords,
            stopword_guard_count=self._stopword_guard_count,
        )

        if not matched:
            return []

        markers = find_singlish_markers(cleaned, self._singlish_lexicon)

        LOGGER.debug(
            "Singlish heuristic matched %d marker(s) %s in %r",
            len(markers),
            markers,
            cleaned[:60],
        )

        return markers

    @staticmethod
    def _load_config_or_raise(
        config_path: Optional[str],
    ) -> Dict[str, Any]:
        """Load the config file, wrapping errors for a clear message."""

        path = config_path or str(DEFAULT_CONFIG_PATH)

        try:
            return load_config(path)
        except FileNotFoundError as error:
            raise LanguageDetectionError(
                f"Language detection config not found at {path}. Pass "
                f"config_path explicitly."
            ) from error
        except ValueError as error:
            raise LanguageDetectionError(
                f"Language detection config is invalid: {error}"
            ) from error

    def _configure_logging(self) -> None:
        """Attach a stdout handler to the package logger once."""

        level_name = str(
            (self.config.get("logging") or {}).get("level", "INFO")
        ).upper()

        level = getattr(logging, level_name, logging.INFO)

        package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
        package_logger.setLevel(level)

        if not package_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-7s | "
                    "%(name)s | %(message)s"
                )
            )
            package_logger.addHandler(handler)
            package_logger.propagate = False

    def _build_cache(
        self, use_cache: Optional[bool]
    ) -> LanguageDetectionCache:
        """Create the result cache from configuration."""

        cache_config = dict(self.config.get("cache") or {})

        if use_cache is not None:
            cache_config["enabled"] = bool(use_cache)

        return LanguageDetectionCache(
            enabled=bool(cache_config.get("enabled", True)),
            redis_url=cache_config.get("redis_url"),
            ttl_seconds=int(cache_config.get("ttl_seconds", 86400)),
            key_prefix=cache_config.get("key_prefix", "langdetect"),
            socket_timeout=float(
                cache_config.get("socket_timeout_seconds", 1.0)
            ),
            max_memory_entries=int(
                cache_config.get("max_memory_entries", 10000)
            ),
        )

    def _build_language_names(self) -> Dict[str, str]:
        """Build the ``language_code -> language name`` mapping."""

        names: Dict[str, str] = {}

        for code, entry in (self.config.get("languages") or {}).items():
            if isinstance(entry, dict):
                names[code] = entry.get("name", code)
            else:
                names[code] = str(entry)

        names.setdefault(CODE_SINHALA, LANGUAGE_SINHALA)
        names.setdefault(CODE_ENGLISH, LANGUAGE_ENGLISH)
        names.setdefault(CODE_SINGLISH, LANGUAGE_SINGLISH)
        names.setdefault(CODE_CODE_MIXED, LANGUAGE_CODE_SWITCHED)
        names.setdefault(CODE_NON_TEXT, LANGUAGE_NON_TEXT)
        names.setdefault(CODE_UNKNOWN, LANGUAGE_UNKNOWN)

        return names

    def _build_model_code_map(self) -> Dict[str, str]:
        """Build the ``fastText code -> language_code`` mapping."""

        mapping: Dict[str, str] = {}

        for code, entry in (self.config.get("languages") or {}).items():
            model_codes = (
                entry.get("model_codes", [])
                if isinstance(entry, dict)
                else []
            )
            for model_code in model_codes:
                mapping[str(model_code).lower()] = code

        special = self.config.get("special_codes") or {}

        for code, entry in special.items():
            model_codes = (
                entry.get("model_codes", [])
                if isinstance(entry, dict)
                else []
            )
            for model_code in model_codes:
                mapping[str(model_code).lower()] = code

        return mapping

    def _map_model_label(self, label: Optional[str]) -> Optional[str]:
        """Map a raw fastText label to a supported language code."""

        if not label:
            return None

        base_code, script = parse_fasttext_label(label)

        if not base_code:
            return None

        mapped = self._model_code_map.get(base_code)

        if mapped:
            return mapped

        if script == "SINH":
            return CODE_SINHALA

        LOGGER.debug(
            "fastText label %s (code=%s, script=%s) is not a supported "
            "language",
            label,
            base_code,
            script,
        )

        return None

    @staticmethod
    def _string_list(value: Any, config_key: str) -> List[str]:
        """Return a config list of words, dropping non-string entries."""

        if not value:
            return []

        if not isinstance(value, (list, tuple)):
            LOGGER.warning(
                "Config key %s must be a list of words, got %s; ignoring",
                config_key,
                type(value).__name__,
            )
            return []

        words = [item for item in value if isinstance(item, str)]
        dropped = len(value) - len(words)

        if dropped:
            LOGGER.warning(
                "Dropped %d non-string entr%s from config key %s. Quote "
                "YAML booleans such as \"yes\", \"no\", \"on\", and \"off\".",
                dropped,
                "y" if dropped == 1 else "ies",
                config_key,
            )

        return words

    def _language_name(self, code: str) -> str:
        """Return the display name for a language code."""

        return self._language_names.get(code, code)

    @staticmethod
    def _classification_report(
        expected: Sequence[str], predicted: Sequence[str]
    ) -> Optional[str]:
        """Return a scikit-learn text report, or None if unavailable."""

        try:
            from sklearn.metrics import classification_report
        except ImportError as error:
            LOGGER.info(
                "scikit-learn not installed, skipping the text report "
                "(%s). Manual precision/recall/F1 is still computed.",
                error,
            )
            return None

        try:
            return classification_report(
                list(expected),
                list(predicted),
                zero_division=0,
                output_dict=False,
            )
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("classification_report failed: %s", error)
            return None

    @staticmethod
    def _metrics_with_sklearn(
        expected: Sequence[str], predicted: Sequence[str]
    ) -> Dict[str, Any]:
        """Compute metrics with scikit-learn."""

        from sklearn.metrics import (
            accuracy_score,
            f1_score,
            precision_recall_fscore_support,
        )

        y_true = list(expected)
        y_pred = list(predicted)

        labels = sorted(set(y_true) | set(y_pred))

        precision, recall, f1, support = precision_recall_fscore_support(
            y_true, y_pred, labels=labels, zero_division=0
        )

        per_language = {
            label: {
                "precision": round(float(p), 4),
                "recall": round(float(r), 4),
                "f1": round(float(f), 4),
                "support": int(s),
            }
            for label, p, r, f, s in zip(
                labels, precision, recall, f1, support
            )
        }

        return {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "macro_f1": float(
                f1_score(
                    y_true, y_pred, average="macro", zero_division=0
                )
            ),
            "weighted_f1": float(
                f1_score(
                    y_true, y_pred, average="weighted", zero_division=0
                )
            ),
            "micro_f1": float(
                f1_score(
                    y_true, y_pred, average="micro", zero_division=0
                )
            ),
            "per_language": per_language,
        }

    @staticmethod
    def _metrics_manual(
        expected: Sequence[str], predicted: Sequence[str]
    ) -> Dict[str, Any]:
        """Compute metrics without scikit-learn."""

        y_true = list(expected)
        y_pred = list(predicted)

        total = len(y_true)
        correct = sum(
            1
            for actual, guess in zip(y_true, y_pred)
            if actual == guess
        )

        labels = sorted(set(y_true) | set(y_pred))

        per_language: Dict[str, Dict[str, Any]] = {}
        f1_sum = 0.0
        weighted_f1_sum = 0.0

        for label in labels:
            true_positive = sum(
                1
                for actual, guess in zip(y_true, y_pred)
                if actual == label and guess == label
            )
            false_positive = sum(
                1
                for actual, guess in zip(y_true, y_pred)
                if actual != label and guess == label
            )
            false_negative = sum(
                1
                for actual, guess in zip(y_true, y_pred)
                if actual == label and guess != label
            )

            support = true_positive + false_negative

            precision = (
                true_positive / (true_positive + false_positive)
                if (true_positive + false_positive)
                else 0.0
            )
            recall = (
                true_positive / (true_positive + false_negative)
                if (true_positive + false_negative)
                else 0.0
            )
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall)
                else 0.0
            )

            per_language[label] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "support": support,
            }

            f1_sum += f1
            weighted_f1_sum += f1 * support

        return {
            "accuracy": correct / total if total else 0.0,
            "macro_f1": f1_sum / len(labels) if labels else 0.0,
            "weighted_f1": (
                weighted_f1_sum / total if total else 0.0
            ),
            "micro_f1": correct / total if total else 0.0,
            "per_language": per_language,
        }

    @staticmethod
    def _top_confusions(
        expected: Sequence[str],
        predicted: Sequence[str],
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return the most frequent expected/predicted mismatches."""

        counts: Dict[tuple, int] = defaultdict(int)

        for actual, guess in zip(expected, predicted):
            if actual != guess:
                counts[(actual, guess)] += 1

        return [
            {
                "expected": pair[0],
                "predicted": pair[1],
                "count": count,
            }
            for pair, count in sorted(
                counts.items(), key=lambda item: item[1], reverse=True
            )[:limit]
        ]

    def _build_result(
        self,
        language: str,
        code: str,
        confidence: float,
        is_code_switched: bool,
        short_text: bool,
        non_text: bool,
        fallback_used: bool = False,
        raw_label: Optional[str] = None,
        source: str = SOURCE_FASTTEXT,
    ) -> Dict[str, Any]:
        """Assemble a result in the canonical shape."""

        return {
            "language": language,
            "language_code": code,
            "confidence": round(float(confidence), 4),
            "is_code_switched": bool(is_code_switched),
            "low_confidence": False,
            "short_text": bool(short_text),
            "non_text": bool(non_text),
            "fallback_used": bool(fallback_used),
            "raw_label": raw_label,
            "source": source,
        }

    def _log_prediction(
        self, raw_text: str, result: Dict[str, Any]
    ) -> None:
        """Log one prediction with every required field."""

        if not self._log_predictions:
            return

        LOGGER.info(
            "detect | text=%s | language=%s (code=%s) | confidence=%.4f "
            "