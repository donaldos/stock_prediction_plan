"""
VectorStore — 전략 위임 클래스 + 파이프라인 오케스트레이터.

EmbeddedChunk 리스트(임베딩 스냅샷) → 벡터DB upsert.

데이터 연결 흐름:
    embeddings.json
      └─ load_embeddings(run_dir) → list[EmbeddedChunk]
            └─ VectorStore.upsert_all(embedded_chunks) → int (upserted count)
                  └─ upsert_and_save(run_dir) → vectordb_meta.json
"""

from __future__ import annotations
import logging
import time
from pathlib import Path

from .base import VectorDBStrategy
from .models import SearchResult
from . import snapshot as snap
from .strategies import ChromaStrategy, PineconeStrategy

logger = logging.getLogger(__name__)

# 전략 이름 → 클래스 레지스트리
_STRATEGY_REGISTRY: dict[str, type[VectorDBStrategy]] = {
    "chroma":   ChromaStrategy,
    "pinecone": PineconeStrategy,
}


def _build_strategy(name: str, **kwargs) -> VectorDBStrategy:
    cls = _STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"알 수 없는 벡터DB 전략: {name!r}. "
            f"사용 가능: {list(_STRATEGY_REGISTRY)}"
        )
    return cls(**kwargs)


class VectorStore:
    """
    전략 패턴 기반 벡터DB 위임 클래스.

    Args:
        strategy: 전략 이름 "chroma" | "pinecone"
        **kwargs: 전략별 파라미터 (persist_dir, collection, api_key 등)

    Example:
        store = VectorStore("chroma", persist_dir="chroma_db")
        count = store.upsert_all(embedded_chunks, collection="stock_rag")
        results = store.search(query_vector, collection="stock_rag", top_k=5)
    """

    def __init__(self, strategy: str = "chroma", **kwargs):
        self._strategy = _build_strategy(strategy, **kwargs)

    @property
    def strategy_name(self) -> str:
        return self._strategy.name

    @property
    def strategy_params(self) -> dict:
        return self._strategy.params

    def upsert_all(self, embedded_chunks: list, collection: str) -> int:
        """
        EmbeddedChunk 리스트를 벡터DB에 upsert.

        Args:
            embedded_chunks: list[EmbeddedChunk]
            collection:      컬렉션(또는 네임스페이스) 이름

        Returns:
            upsert 된 건수
        """
        return self._strategy.upsert(embedded_chunks, collection)

    def search(
        self,
        query_vector: list[float],
        collection: str,
        top_k: int = 5,
        filter_meta: dict | None = None,
    ) -> list[SearchResult]:
        """
        유사 문서 검색.

        Args:
            query_vector: 쿼리 임베딩 벡터
            collection:   검색 대상 컬렉션 이름
            top_k:        반환 결과 수
            filter_meta:  메타데이터 필터 (선택)

        Returns:
            SearchResult 리스트
        """
        return self._strategy.search(query_vector, collection, top_k, filter_meta)


# ── 파이프라인 함수 ─────────────────────────────────────────────

def upsert_and_save(
    run_dir: Path,
    strategy: str = "chroma",
    collection: str = "stock_rag",
    force: bool = False,
    **strategy_kwargs,
) -> Path:
    """
    run_dir 의 embeddings.json 을 읽어 벡터DB에 upsert 후 vectordb_meta.json 저장.

    vectordb_meta.json 이 이미 존재하면 재upsert 없이 경로를 반환한다 (캐시).
    force=True 이면 강제 재upsert.

    Args:
        run_dir:           collected_datas/{YYYY_MMDD_HH}/ 경로
        strategy:          벡터DB 전략 이름 (기본: chroma)
        collection:        컬렉션 이름 (기본: stock_rag)
        force:             True 이면 기존 vectordb_meta.json 무시
        **strategy_kwargs: 전략별 파라미터 (persist_dir, api_key 등)

    Returns:
        저장된 vectordb_meta.json 경로
    """
    from src.pipeline.embedding import load_embeddings

    output_path = run_dir / "vectordb_meta.json"

    # ── 캐시 확인 ────────────────────────────────────────────────
    if not force and snap.exists(output_path):
        logger.info("캐시 사용 — 기존 upsert 결과: %s", snap.summary(output_path))
        return output_path

    # ── 임베딩 로드 ──────────────────────────────────────────────
    embedded_chunks = load_embeddings(run_dir)
    if not embedded_chunks:
        raise FileNotFoundError(
            f"{run_dir / 'embeddings.json'} 없음. 먼저 --embed 를 실행하세요."
        )
    logger.info("임베딩 로드 완료 — %d개 EmbeddedChunk", len(embedded_chunks))

    # ── upsert 실행 ──────────────────────────────────────────────
    store = VectorStore(strategy=strategy, **strategy_kwargs)
    logger.info(
        "벡터DB upsert 시작 — strategy=%s collection=%s params=%s",
        strategy, collection, store.strategy_params,
    )
    t0 = time.perf_counter()
    total = store.upsert_all(embedded_chunks, collection=collection)
    upsert_elapsed = time.perf_counter() - t0

    # source_type 별 집계
    counts: dict[str, int] = {}
    for ec in embedded_chunks:
        counts[ec.source_type] = counts.get(ec.source_type, 0) + 1

    # ── 메타데이터 저장 ──────────────────────────────────────────
    snap.save(
        path=output_path,
        meta={
            "run_dir":        str(run_dir),
            "strategy":       strategy,
            "collection":     collection,
            "strategy_params": store.strategy_params,
            "total_upserted": total,
            "counts":         counts,
        },
    )

    logger.info(
        "벡터DB upsert 완료 — total=%d counts=%s  elapsed=%.2fs",
        total, counts, upsert_elapsed,
    )
    return output_path


def search_similar(
    query_vector: list[float],
    strategy: str = "chroma",
    collection: str = "stock_rag",
    top_k: int = 5,
    filter_meta: dict | None = None,
    **strategy_kwargs,
) -> list[SearchResult]:
    """
    벡터DB에서 유사 문서 검색.
    RAG 단계(LangChain/LangGraph)에서 호출한다.

    Args:
        query_vector:  쿼리 임베딩 벡터
        strategy:      벡터DB 전략 이름 (기본: chroma)
        collection:    검색 대상 컬렉션 이름 (기본: stock_rag)
        top_k:         반환 결과 수 (기본: 5)
        filter_meta:   메타데이터 필터 (선택)
        **strategy_kwargs: 전략별 파라미터

    Returns:
        SearchResult 리스트
    """
    store = VectorStore(strategy=strategy, **strategy_kwargs)
    return store.search(query_vector, collection=collection, top_k=top_k, filter_meta=filter_meta)
