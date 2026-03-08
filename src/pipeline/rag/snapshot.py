"""
RAG 예측 결과 스냅샷 관리.

저장 파일: {run_dir}/prediction_result.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pipeline.rag.models import PredictionOutput

logger = logging.getLogger(__name__)

_FILENAME = "prediction_result.json"


def save(
    output: "PredictionOutput",
    path: Path,
    meta: dict | None = None,
) -> None:
    """
    PredictionOutput을 JSON 파일로 저장.

    Args:
        output: 예측 결과
        path:   저장 경로 (prediction_result.json)
        meta:   추가 메타데이터 (llm_strategy, model_name 등)
    """
    payload = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        **(meta or {}),
        "result": output.to_dict(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.debug("예측 결과 저장: %s", path)


def load(path: Path) -> "PredictionOutput":
    """prediction_result.json을 읽어 PredictionOutput 반환."""
    from src.pipeline.rag.models import PredictionOutput
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return PredictionOutput.from_dict(payload["result"])


def exists(path: Path) -> bool:
    """스냅샷 파일 존재 여부."""
    return path.exists() and path.stat().st_size > 0


def default_path(run_dir: Path) -> Path:
    """run_dir 기준 기본 저장 경로."""
    return run_dir / _FILENAME


def summary(path: Path) -> str:
    """로그용 한 줄 요약."""
    if not exists(path):
        return f"(없음: {path.name})"
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        result = payload.get("result", {})
        strategy = payload.get("llm_strategy", "?")
        model = payload.get("model_name", "?")
        return (
            f"strategy={strategy}  model={model}"
            f"  ticker={result.get('ticker', '?')}"
            f"  prediction={result.get('prediction', '?')}"
            f"  confidence={result.get('confidence_score', '?')}"
            f"  low_confidence={result.get('low_confidence', False)}"
        )
    except Exception as exc:
        return f"(요약 실패: {exc})"
