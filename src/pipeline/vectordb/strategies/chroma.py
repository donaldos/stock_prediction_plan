"""
Chroma 벡터DB 전략.

로컬 파일 시스템에 벡터를 영속 저장하는 오픈소스 벡터DB.
API 키가 필요 없어 파일럿 단계에 적합하다.

설치:
    pip install chromadb

저장 경로:
    {project_root}/{persist_dir}/  (기본: chroma_db/)
    컬렉션 단위로 데이터 분리 가능.
"""

from __future__ import annotations
import hashlib
import logging
from pathlib import Path

from ..base import VectorDBStrategy
from ..models import SearchResult

logger = logging.getLogger(__name__)

_DEFAULT_PERSIST_DIR = "chroma_db"


class ChromaStrategy(VectorDBStrategy):
    """
    Chroma 로컬 벡터DB 전략.

    Args:
        persist_dir:  벡터 저장 디렉토리 (프로젝트 루트 기준, 기본: chroma_db)
        collection:   기본 컬렉션 이름 (기본: stock_rag)
    """

    def __init__(
        self,
        persist_dir: str = _DEFAULT_PERSIST_DIR,
        collection: str = "stock_rag",
    ):
        self._persist_dir = persist_dir
        self._default_collection = collection
        self._clients: dict[str, object] = {}  # collection → ChromaCollection 캐시

    def _get_collection(self, collection: str):
        if collection not in self._clients:
            try:
                import chromadb
            except ImportError as e:
                raise ImportError(
                    "chromadb 가 설치되지 않았습니다. pip install chromadb"
                ) from e

            # 프로젝트 루트 기준 경로 (stock_prediction_plan/)
            persist_path = Path(__file__).resolve().parents[4] / self._persist_dir
            persist_path.mkdir(parents=True, exist_ok=True)

            client = chromadb.PersistentClient(path=str(persist_path))
            self._clients[collection] = client.get_or_create_collection(
                name=collection,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Chroma 컬렉션 연결 — %s @ %s", collection, persist_path)
        return self._clients[collection]

    @staticmethod
    def _chunk_id(embedded_chunk) -> str:
        """청크의 고유 ID 생성 (source + chunk_index + text 앞 64자 해시)."""
        key = f"{embedded_chunk.source}#{embedded_chunk.chunk_index}#{embedded_chunk.text[:64]}"
        return hashlib.md5(key.encode()).hexdigest()

    def upsert(self, embedded_chunks: list, collection: str) -> int:
        col = self._get_collection(collection)

        # 중복 ID 제거 (같은 배치 내 중복 시 Chroma 오류 방지)
        seen: set[str] = set()
        deduped = []
        for ec in embedded_chunks:
            cid = self._chunk_id(ec)
            if cid not in seen:
                seen.add(cid)
                deduped.append(ec)

        if len(deduped) < len(embedded_chunks):
            logger.warning(
                "Chroma upsert 중복 제거 — 원본=%d  고유=%d",
                len(embedded_chunks), len(deduped),
            )

        ids = [self._chunk_id(ec) for ec in deduped]
        embeddings = [ec.embedding for ec in deduped]
        documents = [ec.text for ec in deduped]
        metadatas = [
            {
                "source": ec.source,
                "source_type": ec.source_type,
                "chunk_index": ec.chunk_index,
                "total_chunks": ec.total_chunks,
                **{k: str(v) for k, v in ec.metadata.items()},
            }
            for ec in deduped
        ]

        col.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.debug("Chroma upsert — collection=%s count=%d", collection, len(ids))
        return len(ids)

    def search(
        self,
        query_vector: list[float],
        collection: str,
        top_k: int = 5,
        filter_meta: dict | None = None,
    ) -> list[SearchResult]:
        col = self._get_collection(collection)

        kwargs: dict = {"query_embeddings": [query_vector], "n_results": top_k}
        if filter_meta:
            kwargs["where"] = filter_meta

        results = col.query(**kwargs)
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        return [
            SearchResult(
                text=doc,
                source=meta.get("source", ""),
                source_type=meta.get("source_type", ""),
                score=1.0 - dist,  # cosine distance → similarity
                metadata=meta,
            )
            for doc, meta, dist in zip(docs, metas, dists)
        ]

    @property
    def name(self) -> str:
        return "chroma"

    @property
    def params(self) -> dict:
        return {
            "persist_dir": self._persist_dir,
            "default_collection": self._default_collection,
        }
