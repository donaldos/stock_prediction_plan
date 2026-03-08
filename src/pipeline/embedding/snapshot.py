"""
EmbeddedChunk 스냅샷 저장 / 로드 유틸.

embeddings.json 이 존재하면 재임베딩 없이 EmbeddedChunk 리스트를 반환한다.
다운스트림 단계(vectordb 등)는 이 모듈을 통해 EmbeddedChunk 를 로드한다.
"""

from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import EmbeddedChunk


def save(
    embedded_chunks: list[EmbeddedChunk],
    path: Path,
    meta: dict | None = None,
) -> Path:
    """
    EmbeddedChunk 리스트를 JSON 스냅샷으로 저장.

    Args:
        embedded_chunks: 저장할 EmbeddedChunk 리스트
        path:            저장 파일 경로 (보통 {run_dir}/embeddings.json)
        meta:            추가 메타 (strategy, model, source_chunks, counts 등)

    Returns:
        저장된 파일 경로
    """
    payload = {
        "snapshot_at": datetime.now().isoformat(),
        **(meta or {}),
        "total": len(embedded_chunks),
        "embedded_chunks": [asdict(c) for c in embedded_chunks],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return path


def load(path: Path) -> list[EmbeddedChunk]:
    """
    JSON 스냅샷에서 EmbeddedChunk 리스트 복원.

    Args:
        path: embeddings.json 경로

    Returns:
        EmbeddedChunk 리스트 (파일 없으면 빈 리스트)
    """
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return [
        EmbeddedChunk(
            text=c["text"],
            source=c["source"],
            source_type=c["source_type"],
            chunk_index=c["chunk_index"],
            total_chunks=c["total_chunks"],
            metadata=c.get("metadata", {}),
            embedding=c.get("embedding", []),
            model=c.get("model", ""),
        )
        for c in payload.get("embedded_chunks", [])
    ]


def exists(path: Path) -> bool:
    """스냅샷 파일이 존재하고 비어있지 않은지 확인."""
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("total", 0) > 0
    except Exception:
        return False


def summary(path: Path) -> str:
    """스냅샷 요약 문자열 반환 (로그 출력용)."""
    if not path.exists():
        return "스냅샷 없음"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        snapshot_at = data.get("snapshot_at", "")
        total = data.get("total", 0)
        strategy = data.get("strategy", "")
        model = data.get("model", "")
        counts = data.get("counts", {})
        count_str = ", ".join(f"{k}:{v}" for k, v in counts.items()) if counts else ""
        return (
            f"total={total} ({count_str})"
            f"  strategy={strategy}  model={model}"
            f"  저장시각={snapshot_at[:19]}"
        )
    except Exception:
        return "스냅샷 읽기 실패"
