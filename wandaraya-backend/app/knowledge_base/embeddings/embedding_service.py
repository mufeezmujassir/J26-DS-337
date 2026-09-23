from __future__ import annotations
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
import os
@dataclass
class EmbeddingResult:
    vector:list[float]
    dimension:int
    model_name:str


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

    _model:SentenceTransformer |None=None

    @classmethod
    def _get_model(cls)->SentenceTransformer:
        if cls._model is None:
            cls._model = SentenceTransformer(cls.MODEL_NAME)
        return cls._model

    @classmethod
    def encode(
        cls,
        text:str,
    )->EmbeddingResult:
        clean_text=text.strip()

        if not clean_text:
            raise ValueError("No text provided")

        model = cls._get_model()

        vector = model.encode(clean_text,
                              normalize_embeddings=True,
                              convert_to_numpy=True,
                              show_progress_bar=False,)

        vector_list=vector.tolist()

        if len(vector_list)!=cls.EXPECTED_DIMENSION:
            raise ValueError(
                f"Expected {cls.EXPECTED_DIMENSION} dimensions, "
                f"but found {len(vector_list)}"
            )

        return EmbeddingResult(
            vector=vector_list,
            dimension=len(vector_list),
            model_name=cls.MODEL_NAME,
        )