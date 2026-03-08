"""
LangGraph 파이프라인 실행기.

외부에서 호출하는 진입점:
  - run_pipeline(...)  : 그래프 실행 → 최종 PipelineState 반환
  - run_and_save(...)  : 실행 + 결과 JSON 저장
  - load_result(...)   : orchestration_result.json 로드
"""
from __future__ import annotations

import logging
from datetime import date as _date
from pathlib import Path

from src.pipeline.orchestration import snapshot as snap_mod

logger = logging.getLogger(__name__)


def run_pipeline(
    run_dir: Path,
    ticker: str,
    llm_strategy: str = "claude",
    llm_params: dict | None = None,
    collection: str = "stock_rag",
    store_strategy: str = "chroma",
    store_params: dict | None = None,
    top_k: int = 5,
    top_k_expanded: int = 10,
    target_date: str | None = None,
) -> dict:
    """
    LangGraph 파이프라인 실행.

    Args:
        run_dir:        수집 데이터 폴더 (Phase 1 결과)
        ticker:         예측 대상 종목코드
        llm_strategy:   LLM 전략 ("claude" | "openai")
        llm_params:     LLM 전략 파라미터
        collection:     벡터DB 컬렉션명
        store_strategy: 벡터DB 전략
        store_params:   벡터DB 전략 파라미터
        top_k:          기본 RAG Top-K
        top_k_expanded: 재시도 시 확장 Top-K
        target_date:    예측 기준 날짜 (기본값: 오늘)

    Returns:
        최종 PipelineState dict
    """
    from src.pipeline.orchestration.graph import build_graph

    target_date = target_date or str(_date.today())
    initial_state = {
        "run_dir":        run_dir.as_posix(),
        "ticker":         ticker,
        "target_date":    target_date,
        "collection":     collection,
        "store_strategy": store_strategy,
        "store_params":   store_params or {},
        "llm_strategy":   llm_strategy,
        "llm_params":     llm_params or {},
        "top_k":          top_k,
        "top_k_expanded": top_k_expanded,
        # 런타임 초기값
        "retry_count":    0,
        "use_few_shot":   False,
        "current_top_k":  top_k,
    }

    logger.info(
        "LangGraph 파이프라인 실행 시작 — ticker=%s  llm=%s  date=%s",
        ticker, llm_strategy, target_date,
    )

    graph = build_graph()
    final_state = graph.invoke(initial_state)

    logger.info(
        "LangGraph 파이프라인 완료 — prediction=%s  confidence=%d  retry=%d",
        final_state.get("report", {}).get("prediction"),
        final_state.get("report", {}).get("confidence_score", 0),
        final_state.get("retry_count", 0),
    )
    return final_state


def run_and_save(
    run_dir: Path,
    ticker: str,
    llm_strategy: str = "claude",
    force: bool = False,
    **kwargs,
) -> Path:
    """
    파이프라인 실행 + orchestration_result.json 저장.

    이미 스냅샷이 있으면 건너뜀 (force=True 시 재실행).

    Returns:
        저장된 파일 경로
    """
    output_path = snap_mod.default_path(run_dir)

    if not force and snap_mod.exists(output_path):
        logger.info("캐시 사용 — 오케스트레이션 건너뜀: %s", output_path.name)
        return output_path

    final_state = run_pipeline(
        run_dir=run_dir,
        ticker=ticker,
        llm_strategy=llm_strategy,
        **kwargs,
    )

    snap_mod.save(final_state, output_path)
    return output_path


def load_result(run_dir: Path) -> dict:
    """저장된 orchestration_result.json 로드."""
    return snap_mod.load(snap_mod.default_path(run_dir))
