"""
LangGraph 파이프라인 상태 정의.

PipelineState는 그래프 전체 실행 동안 노드 간 공유되는 데이터를 담는다.
"""
from __future__ import annotations

from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    # ── 입력 (실행 전 설정) ────────────────────────────────────
    run_dir:        str    # Path.as_posix() — 수집 데이터 폴더
    ticker:         str    # 예측 대상 종목코드 (예: "005930")
    target_date:    str    # 예측 기준 날짜 (YYYY-MM-DD)
    collection:     str    # 벡터DB 컬렉션명
    store_strategy: str    # 벡터DB 전략
    store_params:   dict   # 벡터DB 전략 파라미터
    llm_strategy:   str    # LLM 전략 ("claude" | "openai")
    llm_params:     dict   # LLM 전략 파라미터
    top_k:          int    # 기본 RAG Top-K
    top_k_expanded: int    # 재시도 시 확장 Top-K

    # ── 노드 실행 중 채워지는 상태 ───────────────────────────
    collected_data:   dict  # load_data_node 결과
    scenario_type:    str   # detect_scenario_node 결과 (Case C)
    domestic_context: str   # build_context_node 결과 (Case D)
    us_context:       str   # build_context_node 결과 (Case D)
    rag_chunks:       list  # request_llm_node 중간 결과
    main_context:     str   # request_llm_node 중간 결과

    # ── LLM 응답 ─────────────────────────────────────────────
    llm_result: dict  # PredictionOutput.to_dict()

    # ── 재시도 제어 (Case B) ─────────────────────────────────
    retry_count:    int   # 현재 재시도 횟수
    use_few_shot:   bool  # Few-shot 사용 여부
    current_top_k:  int   # 현재 사용 중인 Top-K

    # ── 최종 리포트 ──────────────────────────────────────────
    report: dict   # generate_report_node 결과

    # ── 오류 ─────────────────────────────────────────────────
    error: str     # 오류 발생 시 메시지
