"""
Upstage Solar Embedding 전략.

Upstage의 solar-embedding-1-large 모델을 API로 호출한다.
한국어 특화 고품질 임베딩을 제공한다.

설치:
    pip install openai   # Upstage는 OpenAI 호환 API 제공

환경 변수:
    UPSTAGE_API_KEY — .env 파일에 설정 (https://console.upstage.ai 에서 발급)

모델:
    solar-embedding-1-large  —  차원 4096

병렬 처리:
    max_concurrent 로 동시 배치 요청 수 제어 (I/O bound, ThreadPoolExecutor 사용)
"""

from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..base import EmbeddingStrategy

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.upstage.ai/v1/solar"
_MODEL_ID = "solar-embedding-1-large"
_DIMENSION = 4096
_MAX_BATCH = 100  # Upstage API 배치 한도


class UpstageEmbedder(EmbeddingStrategy):
    """
    Upstage Solar Embedding API 전략.

    Args:
        api_key:        Upstage API 키 (미지정 시 UPSTAGE_API_KEY 환경 변수 사용)
        batch_size:     한 번에 API에 보낼 텍스트 수 (최대 100)
        max_concurrent: 동시 배치 요청 수 (기본 4) — API rate limit 주의
    """

    def __init__(self, api_key: str = "", batch_size: int = 50, max_concurrent: int = 4):
        if not api_key:
            from src.settings import get_upstage_api_key
            api_key = get_upstage_api_key()
        self._api_key = api_key
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
            self._client = OpenAI(api_key=self._api_key, base_url=_BASE_URL)
        return self._client

    def _embed_batch(self, batch_idx: int, batch: list[str]) -> tuple[int, list[list[float]]]:
        """단일 배치 요청 (ThreadPoolExecutor 에서 호출)."""
        client = self._get_client()
        response = client.embeddings.create(input=batch, model=_MODEL_ID)
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
        return "upstage"

    @property
    def model_name(self) -> str:
        return _MODEL_ID

    @property
    def dimension(self) -> int:
        return _DIMENSION

    @property
    def params(self) -> dict:
        return {"batch_size": self._batch_size, "max_concurrent": self._max_concurrent}
