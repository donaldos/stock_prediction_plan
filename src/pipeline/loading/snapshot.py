"""
Document 스냅샷 저장 / 로드 유틸.

loaded_docs.json 이 존재하면 재크롤링 없이 Document 리스트를 반환한다.
다운스트림 단계(청킹 등)는 이 모듈을 통해 Document 를 로드한다.
"""

from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import Document


def save(
    documents: list[Document],
    path: Path,
    meta: dict | None = None,
) -> Path:
    """
    Document 리스트를 JSON 스냅샷으로 저장.

    Args:
        documents: 저장할 Document 리스트
        path:      저장 파일 경로 (보통 {run_dir}/loaded_docs.json)
        meta:      추가 메타 (counts, run_dir 등)

    Returns:
        저장된 파일 경로
    """
    payload = {
        "snapshot_at": datetime.now().isoformat(),
        **(meta or {}),
        "total": len(documents),
        "documents": [asdict(d) for d in documents],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return path


def load(path: Path) -> list[Document]:
    """
    JSON 스냅샷에서 Document 리스트 복원.

    Args:
        path: loaded_docs.json 경로

    Returns:
        Document 리스트 (파일 없으면 빈 리스트)
    """
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return [
        Document(
            text=d["text"],
            source=d["source"],
            source_type=d["source_type"],
            metadata=d.get("metadata", {}),
        )
        for d in payload.get("documents", [])
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
        counts = data.get("counts", {})
        count_str = ", ".join(f"{k}:{v}" for k, v in counts.items()) if counts else ""
        return f"total={total} ({count_str})  저장시각={snapshot_at[:19]}"
    except Exception:
        return "스냅샷 읽기 실패"
