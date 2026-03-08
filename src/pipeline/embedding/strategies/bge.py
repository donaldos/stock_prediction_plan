"""
BAAI/bge-m3 임베딩 전략.

로컬에서 실행하는 다국어 임베딩 모델로 API 키가 필요 없다.
한국어 + 영어 모두 고품질 임베딩을 제공한다.

설치:
    pip install sentence-transformers

모델:
    BAAI/bge-m3  —  차원 1024, 최대 8192 토큰, 다국어 지원
"""

from __future__ import annotations
import logging

from ..base import EmbeddingStrategy

logger = logging.getLogger(__name__)

_MODEL_ID = "BAAI/bge-m3"
_DIMENSION = 1024


class BgeEmbedder(EmbeddingStrategy):
    """
    BAAI/bge-m3 로컬 임베딩 전략.

    Args:
        batch_size: 한 번에 처리할 텍스트 수 (기본 32)
        device:     "cpu" | "cuda" | "mps" — None 이면 자동 선택
    """

    def __init__(self, batch_size: int = 32, device: str | None = None):
        self._batch_size = batch_size
        self._device = device
        self._model = None  # 지연 로딩

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers 가 설치되지 않았습니다. "
                    "pip install sentence-transformers"
                ) from e
            logger.info("bge-m3 모델 로딩 중 — %s", _MODEL_ID)
            self._model = SentenceTransformer(_MODEL_ID, device=self._device)
            logger.info("bge-m3 모델 로딩 완료")
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [v.tolist() for v in vectors]

    @property
    def name(self) -> str:
        return "bge"

    @property
    def model_name(self) -> str:
        return _MODEL_ID

    @property
    def dimension(self) -> int:
        return _DIMENSION

    @property
    def params(self) -> dict:
        return {"batch_size": self._batch_size, "device": self._device}
