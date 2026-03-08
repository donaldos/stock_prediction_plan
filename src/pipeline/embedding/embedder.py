"""
Embedder — 전략 위임 클래스 + 파이프라인 오케스트레이터.

Chunk 리스트(청킹 스냅샷) → EmbeddedChunk 리스트 변환 및 저장.

데이터 연결 흐름:
    chunks.json
      └─ load_chunks(run_dir) → list[Chunk]
            └─ Embedder.embed_all(chunks) → list[EmbeddedChunk]
                  └─ embed_and_save(run_dir) → embeddings.json
"""

from __future__ import annotations
import logging
import time
from pathlib import Path

from .base import EmbeddingStrategy
from .models import EmbeddedChunk
from . import snapshot as snap
from .strategies import BgeEmbedder, UpstageEmbedder, OpenAIEmbedder

logger = logging.getLogger(__name__)

# 전략 이름 → 클래스 레지스트리
_STRATEGY_REGISTRY: dict[str, type[EmbeddingStrategy]] = {
    "bge":     BgeEmbedder,
    "upstage": UpstageEmbedder,
    "openai":  OpenAIEmbedder,
}


def _registry() -> dict[str, type[EmbeddingStrategy]]:
    """임베딩 전략 레지스트리 반환."""
    return _STRATEGY_REGISTRY


def _build_strategy(name: str, **kwargs) -> EmbeddingStrategy:
    cls = _STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"알 수 없는 임베딩 전략: {name!r}. "
            f"사용 가능: {list(_STRATEGY_REGISTRY)}"
        )
    return cls(**kwargs)


class Embedder:
    """
    전략 패턴 기반 임베딩 위임 클래스.

    Args:
        strategy: 전략 이름 "bge" | "upstage" | "openai"
        **kwargs: 전략별 파라미터 (api_key, batch_size, model 등)

    Example:
        embedder = Embedder("bge", batch_size=32)
        embedded = embedder.embed_all(chunks)
    """

    def __init__(self, strategy: str = "bge", **kwargs):
        self._strategy = _build_strategy(strategy, **kwargs)

    @property
    def strategy_name(self) -> str:
        return self._strategy.name

    @property
    def model_name(self) -> str:
        return self._strategy.model_name

    @property
    def dimension(self) -> int:
        return self._strategy.dimension

    @property
    def strategy_params(self) -> dict:
        return self._strategy.params

    def embed_all(self, chunks: list) -> list[EmbeddedChunk]:
        """
        Chunk 리스트 전체를 임베딩.

        Args:
            chunks: list[Chunk] (load_chunks() 반환값)

        Returns:
            전체 EmbeddedChunk 리스트
        """
        texts = [c.text for c in chunks]
        vectors = self._strategy.embed(texts)
        return [
            EmbeddedChunk(
                text=c.text,
                source=c.source,
                source_type=c.source_type,
                chunk_index=c.chunk_index,
                total_chunks=c.total_chunks,
                metadata={
                    **c.metadata,
                    "embedding_strategy": self._strategy.name,
                    "embedding_model": self._strategy.model_name,
                    "embedding_dim": self._strategy.dimension,
                },
                embedding=v,
                model=self._strategy.model_name,
            )
            for c, v in zip(chunks, vectors)
        ]


# ── 파이프라인 함수 ─────────────────────────────────────────────

def embed_and_save(
    run_dir: Path,
    strategy: str = "bge",
    force: bool = False,
    **strategy_kwargs,
) -> Path:
    """
    run_dir 의 chunks.json 을 읽어 임베딩 후 embeddings.json 저장.

    embeddings.json 이 이미 존재하면 재임베딩 없이 경로를 반환한다 (캐시).
    force=True 이면 강제 재임베딩.

    Args:
        run_dir:           collected_datas/{YYYY_MMDD_HH}/ 경로
        strategy:          임베딩 전략 이름 (기본: bge)
        force:             True 이면 기존 embeddings.json 무시
        **strategy_kwargs: 전략별 파라미터 (api_key, batch_size 등)

    Returns:
        저장된 embeddings.json 경로
    """
    from src.pipeline.chunking import load_chunks

    output_path = run_dir / "embeddings.json"

    # ── 캐시 확인 ────────────────────────────────────────────────
    if not force and snap.exists(output_path):
        logger.info("캐시 사용 — 기존 임베딩 결과 로드: %s", snap.summary(output_path))
        return output_path

    # ── 청크 로드 ─────────────────────────────────────────────────
    chunks = load_chunks(run_dir)
    if not chunks:
        raise FileNotFoundError(
            f"{run_dir / 'chunks.json'} 없음. 먼저 --chunk 를 실행하세요."
        )
    logger.info("청크 로드 완료 — %d개 Chunk", len(chunks))

    # ── 임베딩 실행 ──────────────────────────────────────────────
    embedder = Embedder(strategy=strategy, **strategy_kwargs)
    logger.info(
        "임베딩 시작 — strategy=%s model=%s dim=%d params=%s",
        strategy, embedder.model_name, embedder.dimension, embedder.strategy_params,
    )
    t0 = time.perf_counter()
    embedded = embedder.embed_all(chunks)
    embed_elapsed = time.perf_counter() - t0

    # source_type 별 집계
    counts: dict[str, int] = {}
    for ec in embedded:
        counts[ec.source_type] = counts.get(ec.source_type, 0) + 1

    # ── 스냅샷 저장 ──────────────────────────────────────────────
    t1 = time.perf_counter()
    snap.save(
        embedded_chunks=embedded,
        path=output_path,
        meta={
            "run_dir":       str(run_dir),
            "strategy":      strategy,
            "model":         embedder.model_name,
            "dimension":     embedder.dimension,
            "strategy_params": embedder.strategy_params,
            "source_chunks": len(chunks),
            "counts":        counts,
        },
    )
    save_elapsed = time.perf_counter() - t1

    logger.info(
        "임베딩 완료 — total=%d counts=%s  embed_elapsed=%.2fs  save_elapsed=%.2fs",
        len(embedded), counts, embed_elapsed, save_elapsed,
    )
    return output_path


def load_embeddings(run_dir: Path) -> list[EmbeddedChunk]:
    """
    embeddings.json 에서 EmbeddedChunk 리스트 복원.
    벡터DB 저장 단계에서 호출한다.

    Args:
        run_dir: collected_datas/{YYYY_MMDD_HH}/ 경로

    Returns:
        EmbeddedChunk 리스트
    """
    return snap.load(run_dir / "embeddings.json")
