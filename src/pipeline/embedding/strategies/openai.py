"""
OpenAI 임베딩 전략.

OpenAI의 text-embedding-3-small 모델을 API로 호출한다.
비용 대비 성능이 우수하며 다국어 지원이 가능하다.

설치:
    pip install openai

환경 변수:
    OPENAI_API_KEY — .env 파일에 설정 (https://platform.openai.com 에서 발급)

모델 선택:
    text-embedding-3-small  —  차원 1536 (기본, 저비용)
    text-embedding-3-large  —  차원 3072 (고성능, 고비용)

병렬 처리:
    max_concurrent 로 동시 배치 요청 수 제어 (I/O bound, ThreadPoolExecutor 사용)
"""

from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..base import EmbeddingStrategy

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "text-embedding-3-small"
_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002":  1536,
}
_MAX_BATCH = 2048  # OpenAI API 배치 한도


class OpenAIEmbedder(EmbeddingStrategy):
    """
    OpenAI Embedding API 전략.

    Args:
        api_key:        OpenAI API 키 (미지정 시 OPENAI_API_KEY 환경 변수 사용)
        model:          모델 이름 (기본: text-embedding-3-small)
        batch_size:     한 번에 API에 보낼 텍스트 수
        max_concurrent: 동시 배치 요청 수 (기본 8) — RPM/TPM rate limit 주의
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = _DEFAULT_MODEL,
        batch_size: int = 512,
        max_concurrent: int = 8,
    ):
        if not api_key:
            from src.settings import get_openai_api_key
            api_key = get_openai_api_key()
        self._api_key = api_key
        self._model = model
        self._batch_size = min(batch_size, _MAX_BATCH)
        self._max_concurrent = max_concurrent
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise ImportError(
                    "openai 패키지가 설치되지 않았습니다. pip install openai"
                ) from e
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def _embed_batch(self, batch_idx: int, batch: list[str]) -> tuple[int, list[list[float]]]:
        """단일 배치 요청 (ThreadPoolExecutor 에서 호출)."""
        client = self._get_client()
        response = client.embeddings.create(input=batch, model=self._model)
        return batch_idx, [item.embedding for item in response.data]

    def embed(self, texts: list[str]) -> list[list[float]]:
        batches = [
            texts[i : i + self._batch_size]
            for i in range(0, len(texts), self._batch_size)
        ]
        ordered: list[list[list[float]] | None] = [None] * len(batches)

        with ThreadPoolExecutor(max_workers=self._max_concurrent) as pool:
            futures = {
                pool.submit(self._embed_batch, idx, batch): idx
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                idx, vecs = future.result()
                ordered[idx] = vecs
                logger.debug("배치 완료 — %d/%d", idx + 1, len(batches))

        return [vec for batch_vecs in ordered for vec in batch_vecs]  # type: ignore[union-attr]

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return _DIMENSIONS.get(self._model, 1536)

    @property
    def params(self) -> dict:
        return {
            "model": self._model,
            "batch_size": self._batch_size,
            "max_concurrent": self._max_concurrent,
        }
