"""
Chunker — 전략 위임 클래스 + 파이프라인 오케스트레이터.

Document 리스트(로딩 스냅샷) → Chunk 리스트 변환 및 저장.

데이터 연결 흐름:
    loaded_docs.json
      └─ load_snapshot(run_dir) → list[Document]
            └─ Chunker.chunk_all(docs) → list[Chunk]
                  └─ chunk_and_save(run_dir) → chunks.json
"""

from __future__ import annotations
import logging
import time
from pathlib import Path

from .base import ChunkStrategy
from .models import Chunk
from . import snapshot as snap
from .strategies import FixedSizeChunker, RecursiveChunker, SentenceChunker, TokenChunker

logger = logging.getLogger(__name__)

# 전략 이름 → 클래스 레지스트리
_STRATEGY_REGISTRY: dict[str, type[ChunkStrategy]] = {
    "fixed":     FixedSizeChunker,
    "recursive": RecursiveChunker,
    "sentence":  SentenceChunker,
    "token":     TokenChunker,
}


def _build_strategy(name: str, **kwargs) -> ChunkStrategy:
    cls = _STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"알 수 없는 전략: {name!r}. "
            f"사용 가능: {list(_STRATEGY_REGISTRY)}"
        )
    return cls(**kwargs)


class Chunker:
    """
    전략 패턴 기반 청킹 위임 클래스.

    Args:
        strategy: 전략 이름 "fixed" | "recursive" | "sentence" | "token"
        **kwargs: 전략별 파라미터 (chunk_size, overlap, sentences_per_chunk 등)

    Example:
        chunker = Chunker("recursive", chunk_size=500, overlap=50)
        chunks = chunker.chunk_all(documents)
    """

    def __init__(self, strategy: str = "recursive", **kwargs):
        self._strategy = _build_strategy(strategy, **kwargs)

    @property
    def strategy_name(self) -> str:
        return self._strategy.name

    @property
    def strategy_params(self) -> dict:
        return self._strategy.params

    def chunk(self, document) -> list[Chunk]:
        """
        단일 Document → Chunk 리스트.

        Args:
            document: src.data_loading.models.Document

        Returns:
            Chunk 리스트 (빈 Document 면 빈 리스트)
        """
        texts = self._strategy.split(document.text)
        total = len(texts)
        return [
            Chunk(
                text=t,
                source=document.source,
                source_type=document.source_type,
                chunk_index=i,
                total_chunks=total,
                metadata={
                    **document.metadata,
                    "chunk_strategy": self._strategy.name,
                    **{f"chunk_{k}": v for k, v in self._strategy.params.items()},
                },
            )
            for i, t in enumerate(texts)
        ]

    def chunk_all(self, documents: list) -> list[Chunk]:
        """
        Document 리스트 전체를 청킹.

        Args:
            documents: list[Document] (load_snapshot() 반환값)

        Returns:
            전체 Chunk 리스트
        """
        all_chunks: list[Chunk] = []
        for doc in documents:
            all_chunks.extend(self.chunk(doc))
        return all_chunks


# ── 파이프라인 함수 ─────────────────────────────────────────────

def chunk_and_save(
    run_dir: Path,
    strategy: str = "recursive",
    force: bool = False,
    **strategy_kwargs,
) -> Path:
    """
    run_dir 의 loaded_docs.json 을 읽어 청킹 후 chunks.json 저장.

    chunks.json 이 이미 존재하면 재청킹 없이 경로를 반환한다 (캐시).
    force=True 이면 강제 재청킹.

    Args:
        run_dir:           collected_datas/{YYYY_MMDD_HH}/ 경로
        strategy:          청킹 전략 이름 (기본: recursive)
        force:             True 이면 기존 chunks.json 무시
        **strategy_kwargs: 전략별 파라미터

    Returns:
        저장된 chunks.json 경로
    """
    from src.pipeline.loading import load_snapshot

    output_path = run_dir / "chunks.json"

    # ── 캐시 확인 ────────────────────────────────────────────────
    if not force and snap.exists(output_path):
        logger.info("캐시 사용 — 기존 청킹 결과 로드: %s", snap.summary(output_path))
        return output_path

    # ── 스냅샷 로드 ──────────────────────────────────────────────
    documents = load_snapshot(run_dir)
    if not documents:
        raise FileNotFoundError(
            f"{run_dir / 'loaded_docs.json'} 없음. 먼저 --load 를 실행하세요."
        )
    logger.info("스냅샷 로드 완료 — %d개 Document", len(documents))

    # ── 청킹 실행 ────────────────────────────────────────────────
    chunker = Chunker(strategy=strategy, **strategy_kwargs)
    logger.info("청킹 시작 — strategy=%s params=%s", strategy, chunker.strategy_params)
    t0 = time.perf_counter()
    chunks = chunker.chunk_all(documents)
    chunk_elapsed = time.perf_counter() - t0

    # source_type 별 집계
    counts: dict[str, int] = {}
    for c in chunks:
        counts[c.source_type] = counts.get(c.source_type, 0) + 1

    # ── 스냅샷 저장 ──────────────────────────────────────────────
    t1 = time.perf_counter()
    snap.save(
        chunks=chunks,
        path=output_path,
        meta={
            "run_dir":         str(run_dir),
            "strategy":        strategy,
            "strategy_params": chunker.strategy_params,
            "source_docs":     len(documents),
            "counts":          counts,
        },
    )
    save_elapsed = time.perf_counter() - t1

    logger.info("청킹 완료 — total=%d counts=%s  chunk_elapsed=%.2fs  save_elapsed=%.2fs",
                len(chunks), counts, chunk_elapsed, save_elapsed)
    return output_path


def load_chunks(run_dir: Path) -> list[Chunk]:
    """
    chunks.json 에서 Chunk 리스트 복원.
    임베딩 단계에서 호출한다.

    Args:
        run_dir: collected_datas/{YYYY_MMDD_HH}/ 경로

    Returns:
        Chunk 리스트
    """
    return snap.load(run_dir / "chunks.json")
