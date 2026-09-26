from __future__ import annotations

from dataclasses import dataclass
import os

from sentence_transformers import SentenceTransformer


@dataclass
class EmbeddingResult:
    vector: list[float]
    dimension: int
    model_name: str


class AttractionEmbeddingService:

    MODEL_NAME = os.getenv(
        "EMBEDDING_MODEL",
        "BAAI/bge-large-en-v1.5",
    )

    EXPECTED_DIMENSION = int(
        os.getenv(
            "EMBEDDING_DIMENSION",
            "1024",
        )
    )

    _model: SentenceTransformer | None = None

    @classmethod
    def _get_model(cls) -> SentenceTransformer:

        if cls._model is None:
            cls._model = SentenceTransformer(
                cls.MODEL_NAME
            )

        return cls._model

    @classmethod

    def _encode_text(
        cls,
        text: str,
    ) -> EmbeddingResult:
        clean_text = text.strip()

        if not clean_text:
            raise ValueError(
                "Cannot generate embedding for empty text."
            )

        model = cls._get_model()

        vector = model.encode(
            clean_text,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        vector_list = vector.tolist()

        if len(vector_list) != cls.EXPECTED_DIMENSION:
            raise ValueError(
                f"Unexpected embedding dimension: "
                f"{len(vector_list)}. "
                f"Expected: {cls.EXPECTED_DIMENSION}"
            )

        return EmbeddingResult(
            vector=vector_list,
            dimension=len(vector_list),
            model_name=cls.MODEL_NAME,
        )

    @classmethod
    def encode_document(
        cls,
        text: str,
    ) -> EmbeddingResult:

        return cls._encode_text(text)

    @classmethod
    def encode_query(
        cls,

        text: str,
    ) -> EmbeddingResult:
        return cls._encode_text(text)

    @classmethod
    def encode(
        cls,
        text: str,
    ) -> EmbeddingResult:

        return cls.encode_document(text)