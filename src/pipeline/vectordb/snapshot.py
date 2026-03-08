"""
벡터DB upsert 메타데이터 스냅샷 유틸.

벡터 데이터 자체는 DB가 영속 관리하므로 JSON에 저장하지 않는다.
이 모듈은 "이 run_dir 의 임베딩이 이미 upsert 되었는가"를 추적하기 위한
메타데이터(vectordb_meta.json)만 저장/확인한다.
"""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path


def save(
    path: Path,
    meta: dict | None = None,
) -> Path:
    """
    vectordb_meta.json 저장.

    Args:
        path: 저장 파일 경로 ({run_dir}/vectordb_meta.json)
        meta: upsert 메타 (strategy, collection, total_upserted, counts 등)
    """
    payload = {
        "snapshot_at": datetime.now().isoformat(),
        **(meta or {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return path


def exists(path: Path) -> bool:
    """vectordb_meta.json 이 존재하고 upsert 건수가 0 초과인지 확인."""
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("total_upserted", 0) > 0
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
        strategy = data.get("strategy", "")
        collection = data.get("collection", "")
        total = data.get("total_upserted", 0)
        counts = data.get("counts", {})
        count_str = ", ".join(f"{k}:{v}" for k, v in counts.items()) if counts else ""
        return (
            f"total_upserted={total} ({count_str})"
            f"  strategy={strategy}  collection={collection}"
            f"  저장시각={snapshot_at[:19]}"
        )
    except Exception:
        return "스냅샷 읽기 실패"
