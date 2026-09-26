"""Tests for the Wandaraya language detection module.

   python -m pytest tests/test_language_detection.py -v
"""

from __future__ import annotations

import logging
import re
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.onboarding.language_detection.cache import (  # noqa: E402
    BACKEND_DISABLED,
    BACKEND_MEMORY,
    BACKEND_REDIS,
    LanguageDetectionCache,
)
from app.onboarding.language_detection.detector import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    SAMPLE_INPUTS,
    LanguageDetectionError,
    LanguageDetector,
)
from app.onboarding.language_detection.fallback import (  # noqa: E402
    CharacterBasedDetector,
)
from app.onboarding.language_detection.fasttext_model import (  # noqa: E402
    FastTextModel,
    FastTextModelError,
)
from app.onboarding.language_detection.utils import (  # noqa: E402
    build_cache_key,
    clean_text,
    contains_latin,
    contains_only_emoji_or_symbols,
    contains_sinhala,
    deep_merge,
    get_text_length,
    get_word_count,
    is_code_switched,
    is_probably_singlish,
    is_single_short_word,
    is_short_text,
    load_config,
    parse_fasttext_label,
    strip_fasttext_label,
)

PACKAGE_LOGGER_NAME = "app.onboarding.language_detection"

RESULT_KEYS = {
    "language",
    "language_code",
    "confidence",
    "is_code_switched",
    "low_confidence",
    "short_text",
    "non_text",
}

SINHALA_TEXT = "මම කොළඹ යන්න ඕන"
SINGLISH_TEXT = "mama kolamba yanna one"
CODE_MIXED_TEXT = "Beach trip එකට yanna plan karanawa"
HINDI_TEXT = "मैं कोलंबो जाना चाहता हूँ"


class StubFastTextModel:
    """Stand-in for :class:`FastTextModel` with scripted predictions."""

    def __init__(
        self,
        responses: Optional[Dict[str, Tuple[str, float]]] = None,
        default: Tuple[str, float] = ("__label__eng_Latn", 0.99),
        source: str = "stub",
    ) -> None:
        self.responses = responses or {}
        self.default = default
        self._source = source
        self._load_error: Optional[str] = None
        self.predict_calls: List[str] = []
        self.is_loaded = True
        self.model_path = Path("stub://model.bin")
        self.load_error = None

    @property
    def source(self) -> str:
        """Where the stub model came from."""

        return self._source

    def try_load(self) -> bool:
        """The stub is always loaded."""

        return True

    def load(self) -> bool:
        """The stub is always loaded."""

        return True

    def unload(self) -> None:
        """Mark the stub as unloaded."""

        self.is_loaded = False

    def predict(self, text: str) -> Tuple[Optional[str], float]:
        """Return the scripted label for the text."""

        self.predict_calls.append(text)

        for needle, response in self.responses.items():
            if needle in text:
                return response

        return self.default

    def predict_top_k(
        self,
        text: str,
        k: int = 5,
    ) -> List[Tuple[str, float]]:
        """Return the scripted label padded to ``k`` entries."""

        label, confidence = self.predict(text)

        return [(label, confidence)] + [
            ("__label__xxx_Yyyy", 0.0)
        ] * (k - 1)


@pytest.fixture(autouse=True)
def quiet_module_logging():
    """Silence module logging so test output stays readable."""

    package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    previous_level = package_logger.level
    previous_propagate = package_logger.propagate

    package_logger.setLevel(logging.CRITICAL)

    yield

    package_logger.setLevel(previous_level)
    package_logger.propagate = previous_propagate


@pytest.fixture
def base_config() -> Dict[str, Any]:
    """Return the packaged config with caching and logging disabled."""

    config = load_config(str(DEFAULT_CONFIG_PATH))

    config["cache"]["enabled"] = False
    config["logging"]["level"] = "CRITICAL"
    config["logging"]["log_predictions"] = False

    return config


@pytest.fixture
def fallback_detector(base_config) -> LanguageDetector:
    """Return a detector with no model, exercising the fallback path."""

    return LanguageDetector(
        config=base_config,
        use_cache=False,
        auto_load_model=False,
    )


@pytest.fixture
def detector(base_config) -> LanguageDetector:
    """Return a detector with a stub fastText model attached."""

    return LanguageDetector(
        config=base_config,
        use_cache=False,
        model=StubFastTextModel(),
    )


def make_detector(
    config: Dict[str, Any],
    responses: Optional[Dict[str, Tuple[str, float]]] = None,
    default: Tuple[str, float] = ("__label__eng_Latn", 0.99),
) -> LanguageDetector:
    """Build a detector with a scripted stub model."""

    return LanguageDetector(
        config=config,
        use_cache=False,
        model=StubFastTextModel(
            responses=responses,
            default=default,
        ),
    )


class TestScriptDetection:
    """Script and emoji predicates."""

    def test_contains_sinhala_detects_sinhala_block(self):
        assert contains_sinhala(SINHALA_TEXT) is True
        assert contains_sinhala("මම") is True

    def test_contains_sinhala_rejects_latin(self):
        assert contains_sinhala("I want to go to Kandy") is False
        assert contains_sinhala("मैं कोलंबो") is False
        assert contains_sinhala("") is False

    def test_contains_sinhala_handles_non_string(self):
        assert contains_sinhala(None) is False
        assert contains_sinhala(123) is False

    def test_contains_latin_detects_ascii(self):
        assert contains_latin("Kandy") is True

    def test_contains_latin_detects_accented_latin(self):
        assert contains_latin("café") is True
        assert contains_latin("Müller") is True

    def test_contains_latin_excludes_math_symbols(self):
        assert contains_latin("5 × 3") is False
        assert contains_latin("10 ÷ 2") is False

    def test_contains_latin_rejects_sinhala_and_devanagari(self):
        assert contains_latin(SINHALA_TEXT) is False
        assert contains_latin(HINDI_TEXT) is False

    def test_is_code_switched_requires_both_scripts(self):
        assert is_code_switched(CODE_MIXED_TEXT) is True
        assert is_code_switched(SINHALA_TEXT) is False
        assert is_code_switched("just english here") is False
        assert is_code_switched("") is False

    def test_is_code_switched_handles_non_string(self):
        assert is_code_switched(None) is False


class TestEmojiAndSymbols:
    """Emoji and symbol-only detection."""

    @pytest.mark.parametrize(
        "text",
        ["👍", "😀🎉🔥", "!!!", "...", "🙏🏽", "🇱🇰", "❤️"],
    )
    def test_symbol_only_text_is_non_text(self, text):
        assert contains_only_emoji_or_symbols(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "ok",
            "Kandy",
            "මම",
            "123",
            "5",
            "මම 👍",
            "Kandy 👍",
            "$50",
            "a",
        ],
    )
    def test_text_with_letters_or_digits_is_not_non_text(self, text):
        assert contains_only_emoji_or_symbols(text) is False

    def test_empty_and_whitespace_are_not_non_text(self):
        assert contains_only_emoji_or_symbols("") is False
        assert contains_only_emoji_or_symbols("   ") is False

    def test_non_string_is_not_non_text(self):
        assert contains_only_emoji_or_symbols(None) is False
        assert contains_only_emoji_or_symbols(42) is False

    def test_keycap_sequence_counts_as_emoji(self):
        assert contains_only_emoji_or_symbols("1️⃣") is True


class TestTextNormalisation:
    """clean_text, get_text_length, and word counting."""

    def test_clean_text_strips_whitespace(self):
        assert clean_text("  Kandy  ") == "Kandy"

    def test_clean_text_collapses_internal_whitespace(self):
        assert clean_text("go   to\tKandy\nnow") == "go to Kandy now"

    def test_clean_text_normalises_to_nfc(self):
        decomposed = "cafe\u0301"
        assert clean_text(decomposed) == "caf\u00e9"

    def test_clean_text_preserves_sinhala(self):
        assert clean_text(f"  {SINHALA_TEXT} ") == SINHALA_TEXT

    def test_clean_text_handles_non_string(self):
        assert clean_text(None) == ""
        assert clean_text(123) == ""

    def test_get_text_length_excludes_whitespace(self):
        assert get_text_length("go to Kandy") == 9
        assert get_text_length("  ") == 0
        assert get_text_length("මම") == 2

    def test_get_word_count(self):
        assert get_word_count("mama kolamba yanna one") == 4
        assert get_word_count("මම කොළඹ යන්න ඕන") == 4
        assert get_word_count("") == 0

    def test_is_short_text_for_tiny_input(self):
        assert is_short_text("a") is True
        assert is_short_text("") is True

    def test_is_short_text_for_single_short_word(self):
        assert is_short_text("hi") is True
        assert is_short_text("මම") is True

    def test_is_short_text_false_for_longer_input(self):
        assert is_short_text("I want to go to Kandy") is False
        assert is_short_text("මම කොළඹ යන්න ඕන") is False

    def test_is_single_short_word(self):
        assert is_single_short_word("hi") is True
        assert is_single_short_word("මම") is True
        assert is_single_short_word("Kandy") is False
        assert is_single_short_word("go to Kandy") is False


class TestFastTextLabels:
    """Label parsing for lid218e and lid.176 shapes."""

    def test_strip_prefix(self):
        assert strip_fasttext_label("__label__eng_Latn") == "eng_Latn"
        assert strip_fasttext_label("eng_Latn") == "eng_Latn"
        assert strip_fasttext_label(None) == ""

    @pytest.mark.parametrize(
        "label,expected",
        [
            ("__label__eng_Latn", "en"),
            ("__label__sin_Sinh", "si"),
            ("__label__hin_Deva", "hi"),
            ("__label__zho_Hans", "zh"),
            ("__label__deu_Latn", "de"),
            ("__label__fra_Latn", "fr"),
            ("__label__rus_Cyrl", "ru"),
            ("__label__ita_Latn", "it"),
            ("__label__spa_Latn", "es"),
        ],
    )
    def test_parse_iso3_labels(self, label, expected):
        base_code, script = parse_fasttext_label(label)

        assert base_code == expected
        assert script is not None

    def test_parse_lid176_two_letter_labels(self):
        assert parse_fasttext_label("__label__si") == ("si", None)
        assert parse_fasttext_label("__label__en") == ("en", None)

    def test_parse_unknown_language_passes_through(self):
        assert parse_fasttext_label("__label__als_Latn") == (
            "als",
            "LATN",
        )

    def test_parse_language_with_a_known_iso1_equivalent(self):
        base_code, script = parse_fasttext_label("__label__jpn_Jpan")

        assert base_code == "ja"
        assert script == "JPAN"

    def test_parse_sinhala_script_is_preserved(self):
        base_code, script = parse_fasttext_label("__label__sin_Sinh")

        assert base_code == "si"
        assert script == "SINH"

    def test_parse_empty_label(self):
        assert parse_fasttext_label("") == ("", None)
        assert parse_fasttext_label(None) == ("", None)


class TestCacheKey:
    """Cache key construction."""

    def test_key_format(self):
        key = build_cache_key("මම කොළඹ")

        assert key.startswith("langdetect:")
        assert len(key.split(":", 1)[1]) == 64

    def test_key_is_stable(self):
        assert build_cache_key("yanna") == build_cache_key("yanna")

    def test_key_ignores_case_and_surrounding_whitespace(self):
        assert build_cache_key(" Yanna ") == build_cache_key("yanna")

    def test_key_does_not_leak_the_text(self):
        assert "මම" not in build_cache_key("මම කොළඹ")

    def test_key_honours_prefix(self):
        assert build_cache_key("a", prefix="custom").startswith(
            "custom:"
        )


class TestSinglishHeuristic:
    """Romanized-Sinhala lexicon matching."""

    LEXICON = ["mama", "kolamba", "yanna", "one", "kohedha"]
    STOPWORDS = ["i", "want", "to", "the"]

    def test_matches_romanized_sinhala(self):
        assert (
            is_probably_singlish(SINGLISH_TEXT, lexicon=self.LEXICON)
            is True
        )

    def test_rejects_plain_english(self):
        assert (
            is_probably_singlish(
                "I want to go to Kandy",
                lexicon=self.LEXICON,
            )
            is False
        )

    def test_rejects_when_too_few_tokens(self):
        assert (
            is_probably_singlish("mama", lexicon=self.LEXICON) is False
        )

    def test_stopword_guard_suppresses_english(self):
        assert (
            is_probably_singlish(
                "mama yanna one i want the tour",
                lexicon=self.LEXICON,
                stopwords=self.STOPWORDS,
                stopword_guard_count=3,
            )
            is False
        )

    def test_stopword_guard_allows_few_english_words(self):
        assert (
            is_probably_singlish(
                "mama yanna one with the tour",
                lexicon=self.LEXICON,
                stopwords=self.STOPWORDS,
                stopword_guard_count=3,
            )
            is True
        )

    def test_empty_lexicon_never_matches(self):
        assert is_probably_singlish(SINGLISH_TEXT, lexicon=[]) is False

    def test_empty_text_never_matches(self):
        assert is_probably_singlish("", lexicon=self.LEXICON) is False


class TestConfigLoading:
    """Configuration loading, merging, and validation."""

    def test_loads_packaged_config(self):
        config = load_config(str(DEFAULT_CONFIG_PATH))

        assert config["thresholds"]["standard_confidence"] == 0.70
        assert config["thresholds"]["short_text_confidence"] == 0.50
        assert config["thresholds"]["fallback_confidence"] == 0.50
        assert config["cache"]["ttl_seconds"] == 86400
        assert config["model"]["repo_id"] == (
            "facebook/fasttext-language-identification"
        )

    def test_required_languages_are_configured(self):
        config = load_config(str(DEFAULT_CONFIG_PATH))

        for code in (
            "si", "en", "singlish", "code_mixed", "hi", "zh", "de",
            "fr", "ru", "it", "es",
        ):
            assert code in config["languages"], code
            assert config["languages"][code]["name"]

    def test_special_codes_present(self):
        config = load_config(str(DEFAULT_CONFIG_PATH))

        assert "non_text" in config["special_codes"]
        assert "unknown" in config["special_codes"]

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("does/not/exist.yaml")

    def test_empty_file_falls_back_to_defaults(self, tmp_path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("", encoding="utf-8")

        config = load_config(str(empty))

        assert config["thresholds"]["standard_confidence"] == 0.70

    def test_partial_config_is_merged_over_defaults(self, tmp_path):
        partial = tmp_path / "partial.yaml"
        partial.write_text(
            "thresholds:\n  standard_confidence: 0.99\n",
            encoding="utf-8",
        )

        config = load_config(str(partial))

        assert config["thresholds"]["standard_confidence"] == 0.99
        assert config["thresholds"]["fallback_confidence"] == 0.50
        assert "languages" in config

    def test_malformed_yaml_raises(self, tmp_path):
        broken = tmp_path / "broken.yaml"
        broken.write_text("key: [unclosed\n", encoding="utf-8")

        with pytest.raises(ValueError):
            load_config(str(broken))

    def test_non_mapping_yaml_raises(self, tmp_path):
        scalar = tmp_path / "scalar.yaml"
        scalar.write_text("just-a-string\n", encoding="utf-8")

        with pytest.raises(ValueError):
            load_config(str(scalar))

    def test_word_lists_contain_only_strings(self):
        """Regression: unquoted YAML booleans in word lists."""

        config = load_config(str(DEFAULT_CONFIG_PATH))
        singlish = config["singlish"]

        assert singlish["lexicon"], "lexicon must not be empty"

        for word in singlish["lexicon"]:
            assert isinstance(word, str), repr(word)

        for word in singlish["english_stopwords"]:
            assert isinstance(word, str), repr(word)

        assert "yes" in singlish["english_stopwords"]
        assert "no" in singlish["english_stopwords"]
        assert "on" in singlish["english_stopwords"]

    def test_deep_merge_does_not_mutate_inputs(self):
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}

        merged = deep_merge(base, override)

        assert merged == {"a": {"b": 1, "c": 2}}
        assert base == {"a": {"b": 1}}
        assert override == {"a": {"c": 2}}


class TestCharacterBasedFallback:
    """Character-based heuristic detector."""

    def test_sinhala_script(self):
        result = CharacterBasedDetector().detect(SINHALA_TEXT)

        assert result["language"] == "Sinhala"
        assert result["language_code"] == "si"
        assert result["fallback_used"] is True

    def test_short_sinhala_script(self):
        result = CharacterBasedDetector().detect("මම")

        assert result["language_code"] == "si"

    def test_latin_only(self):
        result = CharacterBasedDetector().detect(
            "I want to go to Kandy"
        )

        assert result["language"] == "English"
        assert result["language_code"] == "en"

    def test_mixed_scripts_is_code_switched(self):
        result = CharacterBasedDetector().detect(CODE_MIXED_TEXT)

        assert result["language"] == "Code-Switched"
        assert result["language_code"] == "code_mixed"
        assert result["is_code_switched"] is True

    def test_emoji_only(self):
        result = CharacterBasedDetector().detect("👍")

        assert result["language_code"] == "non_text"
        assert result["non_text"] is True

    def test_empty_text(self):
        result = CharacterBasedDetector().detect("")

        assert result["language_code"] == "unknown"
        assert result["confidence"] == 0.0

    def test_non_string_input(self):
        result = CharacterBasedDetector().detect(None)

        assert result["language_code"] == "unknown"
        assert result["fallback_used"] is True

    @pytest.mark.parametrize(
        "text,expected",
        [
            (HINDI_TEXT, "hi"),
            ("我想去科伦坡", "zh"),
            ("Я хочу поехать в Коломбо", "ru"),
        ],
    )
    def test_other_scripts_map_to_their_language(self, text, expected):
        result = CharacterBasedDetector().detect(text)

        assert result["language_code"] == expected

    def test_unmapped_script_is_unknown_not_english(self):
        result = CharacterBasedDetector().detect("ทะเล")

        assert result["language_code"] == "unknown"

    def test_result_shape_is_complete(self):
        result = CharacterBasedDetector().detect(SINHALA_TEXT)

        assert RESULT_KEYS.issubset(result.keys())

    def test_get_scripts(self):
        detector = CharacterBasedDetector()

        assert detector.get_scripts(CODE_MIXED_TEXT) == [
            "Latin",
            "Sinhala",
        ]


class TestCache:
    """Result cache behaviour and graceful degradation."""

    def test_disabled_cache_is_a_no_op(self):
        cache = LanguageDetectionCache(enabled=False)

        assert cache.backend == BACKEND_DISABLED

        cache.set("මම", {"language_code": "si"})

        assert cache.get("මම") is None

    def test_set_and_get_roundtrip(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        result = {"language": "Sinhala", "language_code": "si"}
        cache.set(SINHALA_TEXT, result)

        assert cache.get(SINHALA_TEXT) == result

    def test_backend_is_redis_or_memory(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        assert cache.backend in {BACKEND_REDIS, BACKEND_MEMORY}

    def test_miss_returns_none(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        assert cache.get("never cached text at all") is None

    def test_lookup_ignores_case_and_whitespace(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        cache.set("Yanna", {"language_code": "singlish"})

        assert cache.get("  yanna  ") is not None

    def test_expired_entry_is_a_miss(self):
        cache = LanguageDetectionCache(
            enabled=True, redis_url=None, ttl_seconds=0
        )

        cache.set("මම", {"language_code": "si"})

        assert cache.get("මම") is None

    def test_delete_removes_entry(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        cache.set("මම", {"language_code": "si"})

        assert cache.delete("මම") is True
        assert cache.get("මම") is None

    def test_clear_empties_the_cache(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        cache.set("මම", {"language_code": "si"})
        cache.set("කොළඹ", {"language_code": "si"})

        cache.clear()

        assert cache.get("මම") is None
        assert cache.get("කොළඹ") is None

    def test_lru_eviction_bounds_memory(self):
        cache = LanguageDetectionCache(
            enabled=True, redis_url=None, max_memory_entries=2
        )

        cache.set("first message here", {"language_code": "en"})
        cache.set("second message here", {"language_code": "en"})
        cache.set("third message here", {"language_code": "en"})

        stats = cache.get_stats()

        assert stats["memory_entries"] <= 2

    def test_malformed_payload_is_dropped(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        key = cache._make_key("මම")
        cache._memory[key] = (float("inf"), "not-a-dict")

        assert cache.get("මම") is None

    def test_non_dict_result_is_refused(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        cache.set("මම", "not a dict")

        assert cache.get("මම") is None

    def test_stats_track_hits_and_misses(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        cache.set("මම", {"language_code": "si"})
        cache.get("මම")
        cache.get("something else entirely")

        stats = cache.get_stats()

        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert 0.0 <= stats["hit_rate"] <= 1.0

    def test_get_with_invalid_input(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        assert cache.get(None) is None
        assert cache.get(123) is None

    def test_close_is_safe_to_call_twice(self):
        cache = LanguageDetectionCache(enabled=True, redis_url=None)

        cache.close()
        cache.close()

        assert cache.get("මම") is None


class FakeFastTextBackend:
    """Minimal stand-in for the compiled ``fasttext`` module."""

    def __init__(
        self,
        labels=("__label__eng_Latn",),
        probabilities=(0.91,),
        fail: bool = False,
        fail_predict: bool = False,
    ) -> None:
        self.labels = labels
        self.probabilities = probabilities
        self.fail = fail
        self.fail_predict = fail_predict
        self.loaded_paths: List[str] = []

    def load_model(self, path: str):
        """Record the path and return a fake model object."""

        self.loaded_paths.append(path)

        if self.fail:
            raise OSError("corrupt model file")

        backend = self

        class Model:
            """Fake fastText model."""

            def predict(self, text, k=1):
                if backend.fail_predict:
                    raise ValueError("prediction exploded")

                if text.endswith("\n"):
                    raise ValueError("text must not end with newline")

                return (
                    backend.labels[:k],
                    backend.probabilities[:k],
                )

        return Model()


@pytest.fixture
def fake_fasttext(monkeypatch):
    """Install a fake ``fasttext`` module and return a factory."""

    def install(backend: FakeFastTextBackend) -> FakeFastTextBackend:
        module = types.ModuleType("fasttext")
        module.load_model = backend.load_model
        monkeypatch.setitem(sys.modules, "fasttext", module)

        return backend

    return install


@pytest.fixture
def model_file(tmp_path) -> Path:
    """Create a placeholder model file on disk."""

    path = tmp_path / "model.bin"
    path.write_bytes(b"not-a-real-fasttext-model")

    return path


class TestFastTextModelWrapper:
    """Model resolution, prediction, and error handling."""

    def test_predict_without_load_raises(self, model_file):
        model = FastTextModel(
            local_path=str(model_file),
            auto_load=False,
        )

        assert model.is_loaded is False

        with pytest.raises(FastTextModelError):
            model.predict("Kandy")

    def test_predict_top_k_without_load_raises(self, model_file):
        model = FastTextModel(
            local_path=str(model_file),
            auto_load=False,
        )

        with pytest.raises(FastTextModelError):
            model.predict_top_k("Kandy")

    def test_missing_binding_is_reported(
        self, model_file, monkeypatch
    ):
        monkeypatch.setitem(sys.modules, "fasttext", None)

        model = FastTextModel(
            local_path=str(model_file),
            auto_load=False,
        )

        with pytest.raises(FastTextModelError) as excinfo:
            model.load()

        assert "fastText binding is not installed" in str(excinfo.value)

    def test_try_load_returns_false_instead_of_raising(
        self, model_file, monkeypatch
    ):
        monkeypatch.setitem(sys.modules, "fasttext", None)

        model = FastTextModel(
            local_path=str(model_file),
            auto_load=False,
        )

        assert model.try_load() is False
        assert model.is_loaded is False
        assert model.load_error

    def test_loads_from_local_file(
        self, model_file, fake_fasttext, tmp_path
    ):
        backend = fake_fasttext(FakeFastTextBackend())

        model = FastTextModel(
            local_path=str(model_file),
            local_dir=str(tmp_path / "cache"),
            auto_load=False,
        )

        assert model.load() is True
        assert model.is_loaded is True
        assert model.source == "local_file"
        assert model.model_path == model_file
        assert backend.loaded_paths == [str(model_file)]

    def test_predict_returns_label_and_confidence(
        self, model_file, fake_fasttext, tmp_path
    ):
        fake_fasttext(FakeFastTextBackend())

        model = FastTextModel(
            local_path=str(model_file),
            local_dir=str(tmp_path / "cache"),
            auto_load=False,
        )
        model.load()

        label, confidence = model.predict("I want to go to Kandy")

        assert label == "__label__eng_Latn"
        assert confidence == pytest.approx(0.91)

    def test_predict_strips_newlines(
        self, model_file, fake_fasttext, tmp_path
    ):
        fake_fasttext(FakeFastTextBackend())

        model = FastTextModel(
            local_path=str(model_file),
            local_dir=str(tmp_path / "cache"),
            auto_load=False,
        )
        model.load()

        label, _ = model.predict("Kandy\nGalle\n")

        assert label == "__label__eng_Latn"

    def test_predict_with_empty_text_returns_none(
        self, model_file, fake_fasttext, tmp_path
    ):
        fake_fasttext(FakeFastTextBackend())

        model = FastTextModel(
            local_path=str(model_file),
            local_dir=str(tmp_path / "cache"),
            auto_load=False,
        )
        model.load()

        assert model.predict("") == (None, 0.0)
        assert model.predict("   ") == (None, 0.0)
        assert model.predict(None) == (None, 0.0)

    def test_predict_failure_returns_none(
        self, model_file, fake_fasttext, tmp_path
    ):
        fake_fasttext(FakeFastTextBackend(fail_predict=True))

        model = FastTextModel(
            local_path=str(model_file),
            local_dir=str(tmp_path / "cache"),
            auto_load=False,
        )
        model.load()

        assert model.predict("Kandy") == (None, 0.0)
        assert model.predict_top_k("Kandy") == []

    def test_predict_top_k_returns_ranked_pairs(
        self, model_file, fake_fasttext, tmp_path
    ):
        fake_fasttext(
            FakeFastTextBackend(
                labels=(
                    "__label__eng_Latn",
                    "__label__nld_Latn",
                    "__label__deu_Latn",
                ),
                probabilities=(0.6, 0.25, 0.15),
            )
        )

        model = FastTextModel(
            local_path=str(model_file),
            local_dir=str(tmp_path / "cache"),
            auto_load=False,
        )
        model.load()

        results = model.predict_top_k("Kandy", k=3)

        assert len(results) == 3
        assert results[0][0] == "__label__eng_Latn"
        assert results[0][1] == pytest.approx(0.6)

    def test_corrupt_model_file_raises(
        self, model_file, fake_fasttext, tmp_path
    ):
        fake_fasttext(FakeFastTextBackend(fail=True))

        model = FastTextModel(
            local_path=str(model_file),
            local_dir=str(tmp_path / "cache"),
            auto_load=False,
        )

        with pytest.raises(FastTextModelError) as excinfo:
            model.load()

        assert "could not be loaded" in str(excinfo.value)
        assert model.is_loaded is False

    def test_local_files_only_without_a_file_raises(self, tmp_path):
        model = FastTextModel(
            local_path=str(tmp_path / "absent.bin"),
            local_dir=str(tmp_path / "cache"),
            local_files_only=True,
            auto_load=False,
        )

        with pytest.raises(FastTextModelError) as excinfo:
            model.load()

        assert "local_files_only" in str(excinfo.value)

    def test_missing_huggingface_hub_is_reported(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setitem(sys.modules, "huggingface_hub", None)

        model = FastTextModel(
            local_path=str(tmp_path / "absent.bin"),
            local_dir=str(tmp_path / "cache"),
            auto_load=False,
        )

        with pytest.raises(FastTextModelError) as excinfo:
            model.load()

        assert "huggingface_hub is required" in str(excinfo.value)

    def test_unload_resets_state(
        self, model_file, fake_fasttext, tmp_path
    ):
        fake_fasttext(FakeFastTextBackend())

        model = FastTextModel(
            local_path=str(model_file),
            local_dir=str(tmp_path / "cache"),
            auto_load=False,
        )
        model.load()
        model.unload()

        assert model.is_loaded is False
        assert model.source == "unavailable"

    def test_get_info_is_serialisable(
        self, model_file, fake_fasttext, tmp_path
    ):
        fake_fasttext(FakeFastTextBackend())

        model = FastTextModel(
            local_path=str(model_file),
            local_dir=str(tmp_path / "cache"),
            auto_load=False,
        )
        model.load()

        info = model.get_info()

        assert info["is_loaded"] is True
        assert info["repo_id"]
        assert info["model_path"] == str(model_file)


class TestDetectorResultShape:
    """The detect() return contract."""

    def test_result_contains_required_keys(self, fallback_detector):
        result = fallback_detector.detect(SINHALA_TEXT)

        assert RESULT_KEYS.issubset(result.keys())

    def test_confidence_is_a_probability(self, fallback_detector):
        for text in (SINHALA_TEXT, "Kandy", "👍", "", "hi"):
            confidence = fallback_detector.detect(text)["confidence"]

            assert 0.0 <= confidence <= 1.0

    def test_non_string_input_returns_unknown(self, fallback_detector):
        for value in (None, 123, 4.5, [], {}, object()):
            result = fallback_detector.detect(value)

            assert result["language_code"] == "unknown"
            assert result["confidence"] == 0.0
            assert "error" in result

    def test_empty_string_returns_unknown(self, fallback_detector):
        result = fallback_detector.detect("")

        assert result["language"] == "unknown"
        assert result["language_code"] == "unknown"
        assert result["short_text"] is True

    def test_whitespace_only_returns_unknown(self, fallback_detector):
        result = fallback_detector.detect("     ")

        assert result["language_code"] == "unknown"
        assert result["short_text"] is True

    def test_language_and_code_are_consistent(self, detector):
        for text in (
            SINHALA_TEXT,
            "I want to go to Kandy",
            CODE_MIXED_TEXT,
        ):
            result = detector.detect(text)
            expected = detector.get_language_info()[
                result["language_code"]
            ]["name"]

            assert result["language"] == expected


class TestNonTextDetection:
    """Emoji-only and symbol-only messages."""

    @pytest.mark.parametrize(
        "text", ["👍", "😀🎉🔥", "🙏🏽", "🇱🇰"]
    )
    def test_emoji_only_is_non_text(self, fallback_detector, text):
        result = fallback_detector.detect(text)

        assert result["language"] == "non-text"
        assert result["language_code"] == "non_text"
        assert result["non_text"] is True
        assert result["confidence"] == 1.0

    def test_emoji_message_is_not_short_text(self, fallback_detector):
        result = fallback_detector.detect("👍")

        assert result["short_text"] is False

    def test_text_with_emoji_is_still_detected(self, fallback_detector):
        result = fallback_detector.detect("Kandy 👍")

        assert result["language_code"] == "en"
        assert result["non_text"] is False

    def test_sinhala_with_emoji_is_sinhala(self, fallback_detector):
        result = fallback_detector.detect("මම කොළඹ 👍")

        assert result["language_code"] == "si"
        assert result["non_text"] is False


class TestShortTextDetection:
    """Short messages use the lowered confidence threshold."""

    def test_single_character_is_unknown(self, fallback_detector):
        result = fallback_detector.detect("a")

        assert result["language_code"] == "unknown"
        assert result["short_text"] is True
        assert result["low_confidence"] is True

    def test_short_english_word(self, fallback_detector):
        result = fallback_detector.detect("hi")

        assert result["language_code"] == "en"
        assert result["short_text"] is True

    def test_short_sinhala_word(self, fallback_detector):
        result = fallback_detector.detect("මම")

        assert result["language_code"] == "si"
        assert result["short_text"] is True

    def test_short_text_uses_the_lower_threshold(self, base_config):
        base_config["thresholds"]["short_text_confidence"] = 0.40
        base_config["thresholds"]["standard_confidence"] = 0.99

        short_result = make_detector(
            base_config,
            responses={"hi": ("__label__eng_Latn", 0.45)},
        ).detect("hi")

        long_result = make_detector(
            base_config,
            responses={"Kandy": ("__label__eng_Latn", 0.45)},
        ).detect("I am going to Kandy tomorrow")

        assert short_result["low_confidence"] is False
        assert long_result["low_confidence"] is True

    def test_longer_input_is_not_short_text(self, fallback_detector):
        result = fallback_detector.detect("I want to go to Kandy")

        assert result["short_text"] is False

    def test_short_text_passes_model_agreement(self, base_config):
        result = make_detector(
            base_config,
            responses={"මම": ("__label__sin_Sinh", 0.93)},
        ).detect("මම")

        assert result["language_code"] == "si"
        assert result["short_text"] is True
        assert result["confidence"] == pytest.approx(0.93)
        assert result["fallback_used"] is False


class TestLocalLanguageDetection:
    """Sinhala, English, Singlish, and code-switched detection."""

    def test_sinhala_script(self, fallback_detector):
        result = fallback_detector.detect(SINHALA_TEXT)

        assert result["language"] == "Sinhala"
        assert result["language_code"] == "si"
        assert result["is_code_switched"] is False
        assert result["low_confidence"] is False

    def test_english(self, detector):
        result = detector.detect("I want to go to Kandy")

        assert result["language"] == "English"
        assert result["language_code"] == "en"
        assert result["is_code_switched"] is False
        assert result["confidence"] == pytest.approx(0.99)

    def test_singlish(self, detector):
        result = detector.detect(SINGLISH_TEXT)

        assert result["language"] == "Singlish"
        assert result["language_code"] == "singlish"

    def test_singlish_not_a_code_switch(self, detector):
        result = detector.detect(SINGLISH_TEXT)

        assert result["is_code_switched"] is False

    def test_code_switched(self, detector):
        result = detector.detect(CODE_MIXED_TEXT)

        assert result["language"] == "Code-Switched"
        assert result["language_code"] == "code_mixed"
        assert result["is_code_switched"] is True

    def test_code_switched_with_model_agreement(self, base_config):
        result = make_detector(
            base_config,
            responses={CODE_MIXED_TEXT: ("__label__eng_Latn", 0.88)},
        ).detect(CODE_MIXED_TEXT)

        assert result["language_code"] == "code_mixed"
        assert result["is_code_switched"] is True
        assert result["fallback_used"] is False
        assert result["confidence"] == pytest.approx(0.88)

    def test_singlish_disabled_by_config(self, base_config):
        base_config["singlish"]["enabled"] = False

        result = make_detector(base_config).detect(SINGLISH_TEXT)

        assert result["language_code"] == "en"

    def test_confident_foreign_language_is_not_relabelled(
        self, base_config
    ):
        result = make_detector(
            base_config,
            responses={
                "mama kolamba yanna": ("__label__fra_Latn", 0.97)
            },
        ).detect("mama kolamba yanna one")

        assert result["language_code"] == "fr"


class TestForeignLanguageDetection:
    """Model-driven detection of the supported foreign languages."""

    @pytest.mark.parametrize(
        "text,label,code,name",
        [
            (HINDI_TEXT, "__label__hin_Deva", "hi", "Hindi"),
            ("我想去科伦坡", "__label__zho_Hans", "zh", "Chinese"),
            (
                "Ich möchte nach Kandy",
                "__label__deu_Latn",
                "de",
                "German",
            ),
            (
                "Je veux aller à Colombo",
                "__label__fra_Latn",
                "fr",
                "French",
            ),
            (
                "Я хочу поехать в Коломбо",
                "__label__rus_Cyrl",
                "ru",
                "Russian",
            ),
            (
                "Voglio andare a Kandy",
                "__label__ita_Latn",
                "it",
                "Italian",
            ),
            (
                "Quiero ir a Kandy",
                "__label__spa_Latn",
                "es",
                "Spanish",
            ),
        ],
    )
    def test_foreign_language_is_mapped(
        self, base_config, text, label, code, name
    ):
        result = make_detector(
            base_config,
            responses={text: (label, 0.93)},
        ).detect(text)

        assert result["language_code"] == code
        assert result["language"] == name
        assert result["fallback_used"] is False
        assert result["low_confidence"] is False

    def test_unsupported_language_is_unknown(self, base_config):
        result = make_detector(
            base_config,
            responses={"supported": ("__label__jpn_Jpan", 0.99)},
        ).detect("some text that is not supported")

        assert result["language_code"] == "unknown"
        assert result["fallback_used"] is False
        assert result["raw_label"] == "__label__jpn_Jpan"

    def test_unsupported_latin_label_on_latin_text_falls_back_to_english(
        self, base_config
    ):
        # lid218e scores bare English place names as unrelated
        # Latin-script languages with high confidence ("Kandy" ->
        # __label__pol_Latn at 0.98). English beats unknown here.
        result = make_detector(
            base_config,
            default=("__label__pol_Latn", 0.98),
        ).detect("Kandy")

        assert result["language_code"] == "en"
        assert result["source"] == "character_heuristic"
        assert result["fallback_used"] is True
        assert result["raw_label"] == "__label__pol_Latn"

    def test_unsupported_latin_label_without_script_falls_back_to_english(
        self, base_config
    ):
        # The smaller lid.176.ftz labels carry no script subtag, so an
        # absent script must count as "no conflict" rather than blocking
        # the fallback.
        result = make_detector(
            base_config,
            default=("__label__pl", 0.97),
        ).detect("Kandy")

        assert result["language_code"] == "en"
        assert result["fallback_used"] is True

    def test_unsupported_non_latin_label_on_latin_text_stays_unknown(
        self, base_config
    ):
        # A model claiming a non-Latin script for Latin text is a real
        # signal that the text is not English.
        result = make_detector(
            base_config,
            default=("__label__tha_Thai", 1.0),
        ).detect("Kandy tour booking")

        assert result["language_code"] == "unknown"
        assert result["fallback_used"] is False

    def test_unsupported_latin_label_on_non_latin_text_stays_unknown(
        self, base_config
    ):
        result = make_detector(
            base_config,
            default=("__label__pol_Latn", 0.99),
        ).detect("こんにちは、元気ですか")

        assert result["language_code"] == "unknown"
        assert result["fallback_used"] is False

    def test_traditional_chinese_maps_to_chinese(self, base_config):
        result = make_detector(
            base_config,
            responses={"supported": ("__label__zho_Hant", 0.91)},
        ).detect("some text that is not supported")

        assert result["language_code"] == "zh"


class TestConfidenceAndFallback:
    """Threshold handling and the character-based fallback route."""

    def test_standard_threshold_flags_low_confidence(self, base_config):
        result = make_detector(
            base_config,
            responses={"beach": ("__label__eng_Latn", 0.72)},
        ).detect("I am planning a beach trip")

        assert result["low_confidence"] is False

        low = make_detector(
            base_config,
            responses={"beach": ("__label__eng_Latn", 0.60)},
        ).detect("I am planning a beach trip")

        assert low["low_confidence"] is True

    def test_below_fallback_threshold_uses_the_fallback(self, base_config):
        result = make_detector(
            base_config,
            responses={"beach": ("__label__eng_Latn", 0.20)},
        ).detect("I am planning a beach trip")

        assert result["fallback_used"] is True
        assert result["source"] == "character_heuristic"

    def test_fallback_threshold_is_configurable(self, base_config):
        base_config["thresholds"]["fallback_confidence"] = 0.10

        result = make_detector(
            base_config,
            responses={"beach": ("__label__eng_Latn", 0.20)},
        ).detect("I am planning a beach trip")

        assert result["fallback_used"] is False
        assert result["confidence"] == pytest.approx(0.20)
        assert result["low_confidence"] is True

    def test_missing_model_uses_the_fallback(self, fallback_detector):
        result = fallback_detector.detect("I want to go to Kandy")

        assert result["fallback_used"] is True
        assert result["source"] == "character_heuristic"
        assert result["language_code"] == "en"

    def test_model_raising_is_survivable(self, base_config):
        class ExplodingModel(StubFastTextModel):
            def predict(self, text):
                raise RuntimeError("model exploded")

        result = LanguageDetector(
            config=base_config,
            use_cache=False,
            model=ExplodingModel(),
        ).detect("I want to go to Kandy")

        assert result["language_code"] == "en"
        assert result["fallback_used"] is True

    def test_script_gate_overrides_a_wrong_model_label(self, base_config):
        result = make_detector(
            base_config,
            responses={SINHALA_TEXT: ("__label__eng_Latn", 0.10)},
        ).detect(SINHALA_TEXT)

        assert result["language_code"] == "si"
        assert result["fallback_used"] is True


class TestBatchDetection:
    """detect_batch ordering and robustness."""

    def test_preserves_order_and_length(self, detector):
        texts = [
            "I want to go to Kandy",
            SINHALA_TEXT,
            SINGLISH_TEXT,
            CODE_MIXED_TEXT,
        ]

        results = detector.detect_batch(texts)

        assert len(results) == len(texts)
        assert [item["language_code"] for item in results] == [
            "en",
            "si",
            "singlish",
            "code_mixed",
        ]

    def test_empty_batch(self, detector):
        assert detector.detect_batch([]) == []

    def test_none_batch_is_survivable(self, detector):
        assert detector.detect_batch(None) == []

    def test_bare_string_is_treated_as_one_item(self, detector):
        results = detector.detect_batch("Kandy")

        assert len(results) == 1
        assert results[0]["language_code"] == "en"

    def test_non_iterable_is_survivable(self, detector):
        assert detector.detect_batch(42) == []

    def test_mixed_invalid_entries(self, detector):
        results = detector.detect_batch(
            ["Kandy", None, 123, SINHALA_TEXT]
        )

        assert len(results) == 4
        assert results[0]["language_code"] == "en"
        assert results[1]["language_code"] == "unknown"
        assert results[2]["language_code"] == "unknown"
        assert results[3]["language_code"] == "si"

    def test_accepts_any_iterable(self, detector):
        results = detector.detect_batch(
            (text for text in ("Kandy", SINHALA_TEXT))
        )

        assert len(results) == 2


class TestSupportedLanguages:
    """get_supported_languages and get_language_info."""

    def test_lists_the_documented_languages(self, detector):
        codes = detector.get_supported_languages()

        for code in (
            "si", "en", "singlish", "code_mixed", "hi", "zh", "de",
            "fr", "ru", "it", "es",
        ):
            assert code in codes

    def test_excludes_special_codes_by_default(self, detector):
        codes = detector.get_supported_languages()

        assert "non_text" not in codes
        assert "unknown" not in codes

    def test_include_special_adds_non_linguistic_codes(self, detector):
        codes = detector.get_supported_languages(include_special=True)

        assert "non_text" in codes
        assert "unknown" in codes

    def test_language_info_has_names(self, detector):
        info = detector.get_language_info()

        assert info["si"]["name"] == "Sinhala"
        assert info["code_mixed"]["name"] == "Code-Switched"
        assert info["singlish"]["name"] == "Singlish"


class TestEvaluation:
    """evaluate() metric computation."""

    def test_perfect_predictions_score_one(self, fallback_detector):
        metrics = fallback_detector.evaluate(
            [
                {"text": SINHALA_TEXT, "language_code": "si"},
                {
                    "text": "I want to go to Kandy",
                    "language_code": "en",
                },
                {
                    "text": CODE_MIXED_TEXT,
                    "language_code": "code_mixed",
                },
            ]
        )

        assert metrics["accuracy"] == 1.0
        assert metrics["macro_f1"] == 1.0
        assert metrics["weighted_f1"] == 1.0
        assert metrics["micro_f1"] == 1.0
        assert metrics["misclassified_count"] == 0

    def test_metrics_shape(self, detector):
        metrics = detector.evaluate(
            [
                {"text": SINHALA_TEXT, "language_code": "si"},
                {
                    "text": "I want to go to Kandy",
                    "language_code": "en",
                },
            ]
        )

        for key in (
            "accuracy",
            "macro_f1",
            "weighted_f1",
            "micro_f1",
            "per_language",
            "confusion",
            "misclassified",
            "total_samples",
            "evaluated_samples",
        ):
            assert key in metrics, key

        assert metrics["per_language"]["si"]["support"] == 1

    def test_wrong_prediction_is_reported(self, base_config):
        metrics = make_detector(
            base_config,
            responses={"english": ("__label__deu_Latn", 0.95)},
        ).evaluate(
            [
                {
                    "text": "some long english sentence here",
                    "language_code": "en",
                }
            ]
        )

        assert metrics["accuracy"] == 0.0
        assert metrics["misclassified_count"] == 1
        assert metrics["misclassified"][0]["predicted"] == "de"
        assert metrics["confusion"][0]["expected"] == "en"
        assert metrics["confusion"][0]["count"] == 1

    def test_accepts_language_name_instead_of_code(self, fallback_detector):
        metrics = fallback_detector.evaluate(
            [{"text": SINHALA_TEXT, "language": "si"}]
        )

        assert metrics["accuracy"] == 1.0

    def test_skips_unusable_samples(self, detector):
        metrics = detector.evaluate(
            [
                {"text": SINHALA_TEXT, "language_code": "si"},
                {"text": "no label here"},
                "not a dict",
            ]
        )

        assert metrics["total_samples"] == 3
        assert metrics["evaluated_samples"] == 1
        assert metrics["skipped_samples"] == 2

    def test_empty_test_data_raises(self, detector):
        with pytest.raises(LanguageDetectionError):
            detector.evaluate([])

    def test_all_unusable_samples_raise(self, detector):
        with pytest.raises(LanguageDetectionError):
            detector.evaluate([{"text": "no label"}])

    def test_sklearn_report_present_when_available(self, detector):
        pytest.importorskip("sklearn.metrics")

        metrics = detector.evaluate(
            [{"text": SINHALA_TEXT, "language_code": "si"}]
        )

        assert isinstance(metrics["sklearn_report"], str)


class TestCacheIntegration:
    """Detector-level cache behaviour."""

    def test_second_detection_is_served_from_cache(self, base_config):
        base_config["cache"]["enabled"] = True

        cached_detector = LanguageDetector(
            config=base_config,
            model=StubFastTextModel(),
        )

        first = cached_detector.detect("මම කොළඹ යන්න ඕන")
        second = cached_detector.detect("මම කොළඹ යන්න ඕන")

        assert first["source"] != "cache"
        assert second["source"] == "cache"
        assert second["language_code"] == first["language_code"]
        assert cached_detector.get_stats()["cache_hits"] == 1

        cached_detector.close()

    def test_disabling_the_cache_avoids_cache_hits(self, detector):
        detector.detect("මම කොළඹ යන්න ඕන")
        detector.detect("මම කොළඹ යන්න ඕන")

        assert detector.get_stats()["cache_hits"] == 0


class TestDetectorStatsAndLifecycle:
    """Stats counters, model loading, and teardown."""

    def test_counters_increment(self, fallback_detector):
        fallback_detector.detect(SINHALA_TEXT)
        fallback_detector.detect("👍")
        fallback_detector.detect("a")
        fallback_detector.detect(None)

        stats = fallback_detector.get_stats()

        assert stats["detections"] == 4
        assert stats["non_text_inputs"] == 1
        assert stats["short_text_inputs"] == 1
        assert stats["invalid_inputs"] == 1
        assert stats["fallback_uses"] >= 1

    def test_thresholds_are_reported(self, detector):
        thresholds = detector.get_stats()["thresholds"]

        assert thresholds["standard_confidence"] == 0.70
        assert thresholds["short_text_confidence"] == 0.50
        assert thresholds["fallback_confidence"] == 0.50

    def test_model_source_reported(self, detector):
        assert detector.get_stats()["model_source"] == "stub"

    def test_load_model_with_no_model_creates_a_wrapper(
        self, base_config, tmp_path
    ):
        base_config["model"] = {
            **base_config["model"],
            "local_path": str(tmp_path / "absent.bin"),
            "local_dir": str(tmp_path / "cache"),
            "local_files_only": True,
        }

        unmodelled = LanguageDetector(
            config=base_config,
            use_cache=False,
            auto_load_model=False,
        )

        assert unmodelled.load_model() is False
        assert unmodelled.get_stats()["model_loaded"] is False
        assert unmodelled.get_stats()["model_error"]

    def test_close_is_safe(self, detector):
        detector.close()
        detector.close()

    def test_missing_config_raises(self):
        with pytest.raises(LanguageDetectionError):
            LanguageDetector(config_path="does/not/exist.yaml")

    def test_config_path_is_used_when_no_config_given(self):
        from_path = LanguageDetector(
            config_path=str(DEFAULT_CONFIG_PATH),
            use_cache=False,
            auto_load_model=False,
        )

        assert "si" in from_path.get_supported_languages()


class TestPredictionLogging:
    """Every prediction is logged with the required fields."""

    def test_prediction_is_logged_with_all_fields(self, caplog):
        package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
        package_logger.setLevel(logging.INFO)
        package_logger.propagate = True

        with caplog.at_level(
            logging.INFO, logger=PACKAGE_LOGGER_NAME
        ):
            config = load_config(str(DEFAULT_CONFIG_PATH))
            config["cache"]["enabled"] = False

            log_detector = LanguageDetector(
                config=config,
                use_cache=False,
                auto_load_model=False,
            )
            log_detector.detect(CODE_MIXED_TEXT)
            log_detector.detect("👍")

        messages = [
            record.getMessage()
            for record in caplog.records
            if "detect |" in record.getMessage()
        ]

        assert len(messages) == 2

        for message in messages:
            for field in (
                "text=",
                "language=",
                "confidence=",
                "fallback=",
                "short_text=",
                "non_text=",
            ):
                assert field in message, field

        assert "code_mixed" in messages[0]
        assert "non_text" in messages[1]

    def test_logging_can_be_disabled(self, caplog, base_config):
        base_config["logging"]["log_predictions"] = False

        with caplog.at_level(
            logging.INFO, logger=PACKAGE_LOGGER_NAME
        ):
            LanguageDetector(
                config=base_config,
                use_cache=False,
                auto_load_model=False,
            ).detect(SINHALA_TEXT)

        assert not [
            record
            for record in caplog.records
            if "detect |" in record.getMessage()
        ]


class TestSampleInputs:
    """The ten documented samples classify correctly."""

    def test_all_ten_samples(self, fallback_detector):
        expected = [
            "en",
            "si",
            "singlish",
            "code_mixed",
            "hi",
            "en",
            "si",
            "non_text",
            "en",
            "unknown",
        ]

        results = fallback_detector.detect_batch(
            [sample["text"] for sample in SAMPLE_INPUTS]
        )

        assert [item["language_code"] for item in results] == expected

    def test_sample_inputs_cover_the_required_cases(self):
        assert len(SAMPLE_INPUTS) == 10

        for sample in SAMPLE_INPUTS:
            assert "text" in sample
            assert "expected" in sample
            assert "expected_code" in sample


class TestModuleContract:
    """The module only detects, and exposes the documented API."""

    def test_package_exports(self):
        from app.onboarding.language_detection import (
            CharacterBasedDetector,
            FastTextModel,
            LanguageDetectionCache,
            LanguageDetector,
        )

        assert LanguageDetector is not None
        assert FastTextModel is not None
        assert CharacterBasedDetector is not None
        assert LanguageDetectionCache is not None

    def test_detector_has_the_public_api(self, detector):
        for method in (
            "detect",
            "detect_batch",
            "get_supported_languages",
            "evaluate",
        ):
            assert callable(getattr(detector, method)), method

    def test_detection_does_not_rewrite_the_input(self, detector):
        text = "  Mama KOLOMBA yanna one  "

        detector.detect(text)

        assert text == "  Mama KOLOMBA yanna one  "

    def test_detection_leaves_no_translation_fields(self, detector):
        result = detector.detect(SINHALA_TEXT)

        for forbidden in (
            "translated_text",
            "normalised_text",
            "segments",
            "translation",
        ):
            assert forbidden not in result


class TestDependencyContract:
    """Dependency pins that the fastText binding needs."""

    @staticmethod
    def _requirements_text() -> str:
        package_root = Path(DEFAULT_CONFIG_PATH).resolve().parent

        return (package_root / "requirements.txt").read_text(
            encoding="utf-8"
        )

    def test_numpy_is_pinned_below_2(self):
        assert re.search(
            r"^numpy[^\n]*<\s*2\s*$",
            self._requirements_text(),
            re.MULTILINE,
        ), "numpy<2 is required by the fastText 0.9.2 binding"

    def test_scipy_and_sklearn_are_capped_for_numpy_1(self):
        text = self._requirements_text()

        # scipy>=1.15 requires numpy>=2.0.0, so an uncapped scipy makes
        # pip resolve to a stack that cannot import.
        assert re.search(
            r"^scipy[^\n]*<\s*1\.15\s*$", text, re.MULTILINE
        )
        assert re.search(
            r"^scikit-learn[^\n]*<\s*1\.7\s*$", text, re.MULTILINE
        )