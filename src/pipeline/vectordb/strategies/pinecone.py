"""
Pinecone 벡터DB 전략.

관리형 클라우드 벡터DB로 대용량 운영 환경에 적합하다.
Chroma 파일럿 이후 전환 대상.

설치:
    pip install pinecone

환경 변수:
    PINECONE_API_KEY — .env 파일에 설정 (https://app.pinecone.io 에서 발급)

특징:
    - namespace 로 컬렉션(종목별) 분리
    - upsert 병렬 처리 지원
    - serverless / pod 선택 가능
"""

from __future__ import annotations
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..base import VectorDBStrategy
from ..models import SearchResult

logger = logging.getLogger(__name__)

_DEFAULT_INDEX = "stock-rag"
_UPSERT_BATCH = 100   # Pinecone upsert 권장 배치 크기
_MAX_CONCURRENT = 4


class PineconeStrategy(VectorDBStrategy):
    """
    Pinecone 클라우드 벡터DB 전략.

    Args:
        api_key:        Pinecone API 키 (미지정 시 PINECONE_API_KEY 환경 변수 사용)
        index_name:     Pinecone 인덱스 이름 (기본: stock-rag)
        max_concurrent: 동시 upsert 배치 요청 수 (기본 4)
    """

    def __init__(
        self,
        api_key: str = "",
        index_name: str = _DEFAULT_INDEX,
        max_concurrent: int = _MAX_CONCURRENT,
    ):
        if not api_key:
            from src.settings import get_pinecone_api_key
            api_key = get_pinecone_api_key()
        self._api_key = api_key
        self._index_name = index_name
        self._max_concurrent = max_concurrent
        self._index = None

    def _get_index(self):
        if self._index is None:
            try:
                from pinecone import Pinecone
            except ImportError as e:
                raise ImportError(
                    "pinecone 패키지가 설치되지 않았습니다. pip install pinecone"
                ) from e
            pc = Pinecone(api_key=self._api_key)
            self._index = pc.Index(self._index_name)
            logger.info("Pinecone 인덱스 연결 — %s", self._index_name)
        return self._index

    @staticmethod
    def _chunk_id(embedded_chunk) -> str:
        key = f"{embedded_chunk.source}#{embedded_chunk.chunk_index}"
        return hashlib.md5(key.encode()).hexdigest()

    def _upsert_batch(self, batch_idx: int, vectors: list, namespace: str) -> tuple[int, int]:
        """단일 배치 upsert (ThreadPoolExecutor 에서 호출)."""
        index = self._get_index()
        index.upsert(vectors=vectors, namespace=namespace)
        return batch_idx, len(vectors)

    def upsert(self, embedded_chunks: list, collection: str) -> int:
        """
        collection 을 Pinecone namespace 로 사용.
        """
        self._get_index()

        vectors = [
            {
                "id": self._chunk_id(ec),
                "values": ec.embedding,
                "metadata": {
                    "text": ec.text,
                    "source": ec.source,
                    "source_type": ec.source_type,
                    "chunk_index": ec.chunk_index,
                    "total_chunks": ec.total_chunks,
                    **{k: str(v) for k, v in ec.metadata.items()},
                },
            }
            for ec in embedded_chunks
        ]

        batches = [
            vectors[i : i + _UPSERT_BATCH]
            for i in range(0, len(vectors), _UPSERT_BATCH)
        ]

        total = 0
        with ThreadPoolExecutor(max_workers=self._max_concurrent) as pool:
            futures = {
                pool.submit(self._upsert_batch, idx, batch, collection): idx
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                _, count = future.result()
                total += count
                logger.debug("Pinecone upsert 배치 완료 — namespace=%s count=%d", collection, count)

        return total

    def search(
        self,
        query_vector: list[float],
        collection: str,
        top_k: int = 5,
        filter_meta: dict | None = None,
    ) -> list[SearchResult]:
        index = self._get_index()

        kwargs: dict = {
            "vector": query_vector,
            "top_k": top_k,
            "namespace": collection,
            "include_metadata": True,
        }
        if filter_meta:
            kwargs["filter"] = filter_meta

        response = index.query(**kwargs)

        return [
            SearchResult(
                text=match["metadata"].get("text", ""),
                source=match["metadata"].get("source", ""),
                source_type=match["metadata"].get("source_type", ""),
                score=match["score"],
                metadata=match["metadata"],
            )
            for match in response["matches"]
        ]

    @property
    def name(self) -> str:
        return "pinecone"

    @property
    def params(self) -> dict:
        return {
            "index_name": self._index_name,
            "max_concurrent": self._max_concurrent,
        }
