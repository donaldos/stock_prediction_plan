"""
오케스트레이션 결과 스냅샷 관리.

저장 파일: {run_dir}/orchestration_result.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_FILENAME = "orchestration_result.json"


def save(state: dict, path: Path) -> None:
    """최종 PipelineState를 JSON 파일로 저장."""
    # 직렬화 불가능한 복잡 객체 제거 후 저장
    serializable = {
        "saved_at":     datetime.now().isoformat(timespec="seconds"),
        "ticker":       state.get("ticker"),
        "target_date":  state.get("target_date"),
        "llm_strategy": state.get("llm_strategy"),
        "scenario_type": state.get("scenario_type"),
        "retry_count":  state.get("retry_count", 0),
        "report":       state.get("report", {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    logger.debug("오케스트레이션 결과 저장: %s", path)


def load(path: Path) -> dict:
    """orchestration_result.json 로드."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def exists(path: Path) -> bool:
    """스냅샷 파일 존재 여부."""
    return path.exists() and path.stat().st_size > 0


def default_path(run_dir: Path) -> Path:
    return run_dir / _FILENAME


def summary(path: Path) -> str:
    """로그용 한 줄 요약."""
    if not exists(path):
        return f"(없음: {path.name})"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        report = data.get("report", {})
        return (
            f"llm={data.get('llm_strategy', '?')}"
            f"  ticker={data.get('ticker', '?')}"
            f"  scenario={data.get('scenario_type', '?')}"
            f"  prediction={report.get('prediction', '?')}"
            f"  confidence={report.get('confidence_score', '?')}"
            f"  retry={data.get('retry_count', 0)}"
            f"  low_conf={report.get('low_confidence', False)}"
        )
    except Exception as exc:
        return f"(요약 실패: {exc})"
