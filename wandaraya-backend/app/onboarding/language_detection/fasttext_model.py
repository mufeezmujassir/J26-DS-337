"""fastText model loader and prediction wrapper."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

from app.onboarding.language_detection.utils import (
    clean_text,
    resolve_project_root,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_REPO_ID = "facebook/fasttext-language-identification"
DEFAULT_FILENAME = "model.bin"
DEFAULT_LOCAL_DIR = "models/fasttext-language-identification"
DEFAULT_ENV_DIR_OVERRIDE = "WANDARAYA_LANGDETECT_MODEL_DIR"

SOURCE_LOCAL_FILE = "local_file"
SOURCE_HUB_DOWNLOAD = "huggingface_hub_download"
SOURCE_UNAVAILABLE = "unavailable"

LOCAL_FILES_ONLY_ENV = "HF_HUB_OFFLINE"


class FastTextModelError(RuntimeError):
    """Raised when the fastText model cannot be downloaded or loaded."""


class FastTextModel:
    """Loads and runs the pre-trained fastText language identifier.

    Model resolution order: ``local_path`` → cached ``local_dir/file``
    → Hugging Face download.
    """

    def __init__(
        self,
        repo_id: str = DEFAULT_REPO_ID,
        filename: str = DEFAULT_FILENAME,
        local_dir: str = DEFAULT_LOCAL_DIR,
        local_path: Optional[str] = None,
        local_files_only: bool = False,
        auto_load: bool = True,
    ) -> None:
        """Create the wrapper and, unless disabled, load the model."""

        self.repo_id = repo_id
        self.filename = filename
        self.local_files_only = local_files_only
        self.env_dir_override = DEFAULT_ENV_DIR_OVERRIDE

        self._model: Optional[Any] = None
        self._model_path: Optional[Path] = None
        self._source: str = SOURCE_UNAVAILABLE
        self._load_error: Optional[str] = None

        self.local_dir = self._resolve_local_dir(local_dir)
        self.local_path = (
            Path(local_path).expanduser() if local_path else None
        )

        if auto_load:
            self.try_load()

    @property
    def is_loaded(self) -> bool:
        """True when a model is loaded and ready to predict."""

        return self._model is not None

    @property
    def source(self) -> str:
        """Where the loaded model came from: local_file, HF, unavailable."""

        return self._source

    @property
    def model_path(self) -> Optional[Path]:
        """Absolute path of the loaded model file, if any."""

        return self._model_path

    @property
    def load_error(self) -> Optional[str]:
        """Message from the most recent failed load, if it failed."""

        return self._load_error

    def load(self) -> bool:
        """Resolve, download if needed, and load the model.

        Raises:
            FastTextModelError: If the model cannot be located,
                downloaded, or loaded.
        """

        self._load_error = None

        model_path, source = self._resolve_model_file()

        fasttext = self._import_fasttext()

        try:
            model = fasttext.load_model(str(model_path))
        except Exception as error:  # noqa: BLE001
            self._load_error = str(error)
            self._source = SOURCE_UNAVAILABLE
            self._model = None
            self._model_path = model_path

            raise FastTextModelError(
                f"fastText model file found at {model_path} but could "
                f"not be loaded: {error}"
            ) from error

        self._model = model
        self._model_path = model_path
        self._source = source

        LOGGER.info(
            "fastText language model loaded from %s (source=%s, repo=%s, "
            "size=%.1f MB)",
            model_path,
            source,
            self.repo_id,
            model_path.stat().st_size / (1024 * 1024),
        )

        return True

    def try_load(self) -> bool:
        """Load the model without raising. Returns True on success."""

        if self.is_loaded:
            return True

        try:
            return self.load()
        except FastTextModelError as error:
            self._load_error = str(error)
            self._source = SOURCE_UNAVAILABLE

            LOGGER.warning(
                "fastText language model unavailable, detection will fall "
                "back to character heuristics. Reason: %s",
                error,
            )

            return False

    def unload(self) -> None:
        """Drop the in-memory model and reset load state."""

        self._model = None
        self._model_path = None
        self._source = SOURCE_UNAVAILABLE

    def predict(self, text: str) -> Tuple[Optional[str], float]:
        """Return the top ``(label, confidence)`` for the text.

        Raises:
            FastTextModelError: If the model is not loaded.
        """

        if not self.is_loaded:
            raise FastTextModelError(
                "fastText model is not loaded. Call load() or "
                "construct FastTextModel with auto_load=True."
            )

        cleaned = self._prepare_input(text)

        if not cleaned:
            return None, 0.0

        try:
            labels, probabilities = self._model.predict(cleaned)
        except Exception as error:  # noqa: BLE001
            LOGGER.warning(
                "fastText prediction failed for text of length %d: %s",
                len(cleaned),
                error,
            )

            return None, 0.0

        if not labels or len(labels) == 0:
            return None, 0.0

        confidence = (
            float(probabilities[0])
            if probabilities is not None and len(probabilities) > 0
            else 0.0
        )

        return str(labels[0]), confidence

    def predict_top_k(
        self,
        text: str,
        k: int = 5,
    ) -> List[Tuple[str, float]]:
        """Return the top-k ``(label, confidence)`` pairs, best first.

        Raises:
            FastTextModelError: If the model is not loaded.
        """

        if not self.is_loaded:
            raise FastTextModelError(
                "fastText model is not loaded. Call load() or "
                "construct FastTextModel with auto_load=True."
            )

        cleaned = self._prepare_input(text)

        if not cleaned:
            return []

        k = max(1, int(k))

        try:
            labels, probabilities = self._model.predict(cleaned, k=k)
        except Exception as error:  # noqa: BLE001
            LOGGER.warning(
                "fastText top-%d prediction failed for text of length "
                "%d: %s",
                k,
                len(cleaned),
                error,
            )

            return []

        results: List[Tuple[str, float]] = []

        for index, label in enumerate(labels or []):
            probability = (
                float(probabilities[index])
                if probabilities is not None
                and index < len(probabilities)
                else 0.0
            )

            results.append((str(label), probability))

        return results

    def get_info(self) -> dict:
        """Return a serialisable snapshot of loader state for debugging."""

        return {
            "repo_id": self.repo_id,
            "filename": self.filename,
            "local_dir": str(self.local_dir),
            "model_path": (
                str(self._model_path) if self._model_path else None
            ),
            "is_loaded": self.is_loaded,
            "source": self._source,
            "load_error": self._load_error,
        }

    @staticmethod
    def _import_fasttext() -> Any:
        """Import the fastText binding.

        Raises:
            FastTextModelError: If the binding cannot be imported.
        """

        try:
            import fasttext  # type: ignore

            return fasttext
        except ImportError as error:
            raise FastTextModelError(
                "The fastText binding is not installed. Install it with "
                "'pip install fasttext' (Linux/macOS) or "
                "'pip install fasttext-wheel' (Windows, prebuilt wheel). "
                f"Import error: {error}"
            ) from error

    def _resolve_local_dir(self, local_dir: str) -> Path:
        """Resolve the cache directory, honouring the env override."""

        override = os.getenv(self.env_dir_override)

        if override:
            LOGGER.info(
                "Language detection model directory overridden by %s=%s",
                self.env_dir_override,
                override,
            )

            return Path(override).expanduser()

        path = Path(local_dir).expanduser()

        if path.is_absolute():
            return path

        return (resolve_project_root() / path).resolve()

    def _resolve_model_file(self) -> Tuple[Path, str]:
        """Locate the model file, downloading it when necessary.

        Raises:
            FastTextModelError: If the file is missing and cannot be
                downloaded.
        """

        if self.local_files_only:
            os.environ.setdefault(LOCAL_FILES_ONLY_ENV, "1")

        candidates: List[Path] = []

        if self.local_path:
            candidates.append(self.local_path)

        candidates.append(self.local_dir / self.filename)

        for candidate in candidates:
            if candidate.is_file():
                LOGGER.debug(
                    "Using cached fastText model at %s", candidate
                )

                return candidate, SOURCE_LOCAL_FILE

        if self.local_path:
            LOGGER.warning(
                "Configured local_path %s does not exist",
                self.local_path,
            )

        if self.local_files_only:
            raise FastTextModelError(
                f"No local fastText model found and local_files_only is "
                f"enabled. Expected one of: "
                f"{', '.join(str(item) for item in candidates)}"
            )

        return self._download_model(candidates)

    def _download_model(
        self,
        candidates: List[Path],
    ) -> Tuple[Path, str]:
        """Download the model from Hugging Face into the cache directory.

        Raises:
            FastTextModelError: If huggingface_hub is missing or the
                download fails.
        """

        try:
            from huggingface_hub import hf_hub_download
        except ImportError as error:
            raise FastTextModelError(
                "huggingface_hub is required to download the fastText "
                "model. Install it with 'pip install huggingface_hub', or "
                "point model.local_path at an existing .bin file. "
                f"Import error: {error}"
            ) from error

        self.local_dir.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            "Downloading fastText model %s/%s into %s (this happens once)",
            self.repo_id,
            self.filename,
            self.local_dir,
        )

        try:
            downloaded = hf_hub_download(
                repo_id=self.repo_id,
                filename=self.filename,
                local_dir=str(self.local_dir),
            )
        except Exception as error:  # noqa: BLE001
            raise FastTextModelError(
                f"Failed to download fastText model "
                f"{self.repo_id}/{self.filename} into {self.local_dir}: "
                f"{error}. Check network access, or set model.local_path "
                f"to a pre-downloaded .bin file. Searched: "
                f"{', '.join(str(item) for item in candidates)}"
            ) from error

        downloaded_path = Path(downloaded)

        if not downloaded_path.is_file():
            raise FastTextModelError(
                f"Hugging Face reported {downloaded_path} as downloaded "
                f"but the file is not present."
            )

        LOGGER.info(
            "Downloaded fastText model to %s (%.1f MB)",
            downloaded_path,
            downloaded_path.stat().st_size / (1024 * 1024),
        )

        return downloaded_path, SOURCE_HUB_DOWNLOAD

    @staticmethod
    def _prepare_input(text: str) -> str:
        """Normalise text into the single-line form fastText accepts."""

        if not isinstance(text, str):
            return ""

        cleaned = clean_text(text)

        if not cleaned:
            return ""

        return cleaned.replace("\n", " ").replace("\r", " ")


def load_model(config: Optional[dict] = None) -> FastTextModel:
    """Build a :class:`FastTextModel` from the module configuration."""

    if config is None:
        from app.onboarding.language_detection.utils import (
            load_config,
        )

        config = load_config(
            str(Path(__file__).resolve().parent / "config.yaml")
        )

    return FastTextModel(
        repo_id=config.get("repo_id", DEFAULT_REPO_ID),
        filename=config.get("filename", DEFAULT_FILENAME),
        local_dir=config.get("local_dir", DEFAULT_LOCAL_DIR),
        local_path=config.get("local_path"),
        local_files_only=bool(config.get("local_files_only", False)),
        auto_load=True,
    )