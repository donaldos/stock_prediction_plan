"""
LangGraph 파이프라인 노드 구현.

노드 목록:
  - load_data       : 수집 데이터 로드
  - detect_scenario : Case C — 미국 반도체 지수 기반 시나리오 감지
  - build_context   : Case D — 멀티종목 컨텍스트 구성
  - request_llm     : RAG 검색 + LLM 예측 요청
  - validate_resp   : Case B — 신뢰도 검증 (conditional edge 판단)
  - retry           : 재시도 파라미터 조정
  - generate_report : 최종 리포트 구조 생성
"""
from __future__ import annotations

import logging
from datetime import date as _date
from pathlib import Path

from src.pipeline.orchestration.state import PipelineState

logger = logging.getLogger(__name__)

# Case B 신뢰도 기준
_MIN_CONFIDENCE = 7
_MIN_EVIDENCE   = 3
_MAX_RETRIES    = 3


# ── 노드 함수 ─────────────────────────────────────────────────────

def load_data(state: PipelineState) -> PipelineState:
    """
    수집 데이터 폴더에서 JSON 파일을 읽어 collected_data로 저장.

    Phase 5 context.py의 load_collected_data() 재사용.
    """
    from src.pipeline.rag.context import load_collected_data
    run_dir = Path(state["run_dir"])
    logger.info("[load_data] 수집 데이터 로드: %s", run_dir.name)
    collected_data = load_collected_data(run_dir)
    logger.info("[load_data] 로드 완료 — 항목 수: %d", len(collected_data))
    return {**state, "collected_data": collected_data}


def detect_scenario(state: PipelineState) -> PipelineState:
    """
    Case C: 미국 반도체 지수 기반 시나리오 감지.

    SOX + 미국 5종목 평균 변동이 모두 ±3% 이상이면 외부충격 시나리오.
    """
    from src.pipeline.rag.context import detect_scenario as _detect
    collected = state.get("collected_data", {})
    scenario = _detect(collected)
    logger.info("[detect_scenario] 시나리오: %s", scenario)
    return {**state, "scenario_type": scenario}


def build_context(state: PipelineState) -> PipelineState:
    """
    Case D: 국내 참고 종목 + 미국 참고 종목 컨텍스트 블록 구성.

    domestic_context, us_context를 상태에 저장.
    current_top_k 초기화 (없으면 top_k 사용).
    """
    from src.pipeline.rag.context import build_domestic_context, build_us_context
    collected = state.get("collected_data", {})

    domestic_tickers = ["042700", "TBD", "000660"]
    us_tickers       = ["NVDA", "AMD", "INTC", "AVGO", "QCOM"]

    domestic_ctx = build_domestic_context(collected, domestic_tickers)
    us_ctx       = build_us_context(collected, us_tickers)

    logger.info("[build_context] 컨텍스트 구성 완료")
    return {
        **state,
        "domestic_context": domestic_ctx,
        "us_context":       us_ctx,
        "current_top_k":    state.get("current_top_k", state.get("top_k", 5)),
        "retry_count":      state.get("retry_count", 0),
        "use_few_shot":     state.get("use_few_shot", False),
    }


def request_llm(state: PipelineState) -> PipelineState:
    """
    RAG 검색 + LLM 예측 요청.

    1. 벡터DB에서 관련 청크 검색 (top_k)
    2. 메인 컨텍스트 구성
    3. 프롬프트 빌드 (시나리오 + few_shot 적용)
    4. LLM 호출 → llm_result 저장
    """
    from src.pipeline.rag.context import build_main_context
    from src.pipeline.rag.prompt import build_messages
    from src.pipeline.rag.predictor import _registry

    run_dir        = Path(state["run_dir"])
    ticker         = state["ticker"]
    target_date    = state.get("target_date", str(_date.today()))
    scenario_type  = state.get("scenario_type", "일반")
    domestic_ctx   = state.get("domestic_context", "")
    us_ctx         = state.get("us_context", "")
    current_top_k  = state.get("current_top_k", state.get("top_k", 5))
    use_few_shot   = state.get("use_few_shot", False)
    llm_strategy   = state["llm_strategy"]
    llm_params     = state.get("llm_params", {})
    collection     = state.get("collection", "stock_rag")
    store_strategy = state.get("store_strategy", "chroma")
    store_params   = state.get("store_params", {})

    logger.info(
        "[request_llm] LLM=%s  top_k=%d  few_shot=%s  retry=%d",
        llm_strategy, current_top_k, use_few_shot, state.get("retry_count", 0),
    )

    # RAG 검색
    rag_chunks = _search_rag(
        ticker=ticker,
        run_dir=run_dir,
        top_k=current_top_k,
        collection=collection,
        store_strategy=store_strategy,
        store_params=store_params,
    )

    # 메인 컨텍스트 구성
    collected = state.get("collected_data", {})
    main_ctx = build_main_context(ticker, collected, rag_chunks)

    # 프롬프트 빌드
    messages = build_messages(
        ticker=ticker,
        date=target_date,
        main_context=main_ctx,
        domestic_context=domestic_ctx,
        us_context=us_ctx,
        scenario_type=scenario_type,
        use_few_shot=use_few_shot,
    )

    # LLM 호출
    registry = _registry()
    if llm_strategy not in registry:
        raise ValueError(f"알 수 없는 LLM 전략: '{llm_strategy}'")

    llm = registry[llm_strategy](**llm_params)
    result = llm.predict(messages)
    result.scenario_type = scenario_type  # 일관성 보장

    logger.info(
        "[request_llm] 예측 완료 — prediction=%s  confidence=%d  evidence=%d",
        result.prediction, result.confidence_score, result.evidence_count,
    )

    return {
        **state,
        "rag_chunks":   rag_chunks,
        "main_context": main_ctx,
        "llm_result":   result.to_dict(),
    }


def validate_resp(state: PipelineState) -> str:
    """
    Case B: 신뢰도 검증 — conditional edge 판단 함수.

    Returns:
        "pass"         : 검증 통과 → generate_report 이동
        "retry"        : 재시도 가능 → retry 노드 이동
        "force_report" : 3차 실패 → 강제 리포트 생성
    """
    result       = state.get("llm_result", {})
    retry_count  = state.get("retry_count", 0)
    score        = result.get("confidence_score", 0)
    evidence     = result.get("evidence_count", 0)

    score_ok    = score    >= _MIN_CONFIDENCE
    evidence_ok = evidence >= _MIN_EVIDENCE

    if score_ok and evidence_ok:
        logger.info("[validate_resp] 검증 통과 — confidence=%d  evidence=%d", score, evidence)
        return "pass"

    logger.warning(
        "[validate_resp] 검증 실패 (retry_count=%d) — confidence=%d (기준≥%d)  evidence=%d (기준≥%d)",
        retry_count, score, _MIN_CONFIDENCE, evidence, _MIN_EVIDENCE,
    )

    if retry_count < _MAX_RETRIES:
        return "retry"
    return "force_report"


def retry(state: PipelineState) -> PipelineState:
    """
    재시도 파라미터 조정.

    retry_count에 따라:
      0 → 1차: top_k 확장
      1 → 2차: few_shot 활성화
      2 → 3차: (force_report로 분기되므로 여기는 도달 안 함)
    """
    retry_count   = state.get("retry_count", 0) + 1
    top_k_expanded = state.get("top_k_expanded", 10)

    if retry_count == 1:
        logger.info("[retry] 1차 재시도 — top_k 확장: %d", top_k_expanded)
        return {**state, "retry_count": retry_count, "current_top_k": top_k_expanded}
    else:
        logger.info("[retry] 2차 재시도 — few_shot 활성화")
        return {**state, "retry_count": retry_count, "use_few_shot": True}


def generate_report(state: PipelineState) -> PipelineState:
    """
    최종 리포트 구조 생성.

    llm_result를 기반으로 report dict를 구성한다.
    Phase 7 (Slack 발송)에서 이 report를 포맷팅한다.
    """
    result      = state.get("llm_result", {})
    retry_count = state.get("retry_count", 0)
    low_conf    = retry_count >= _MAX_RETRIES

    report = {
        **result,
        "low_confidence":  low_conf,
        "retry_count":     retry_count,
        "scenario_type":   state.get("scenario_type", "일반"),
        "rag_chunk_count": len(state.get("rag_chunks", [])),
    }

    logger.info(
        "[generate_report] 리포트 생성 완료 — prediction=%s  confidence=%d  low_conf=%s",
        result.get("prediction"), result.get("confidence_score"), low_conf,
    )
    return {**state, "report": report}


def force_report(state: PipelineState) -> PipelineState:
    """
    3차 실패 후 강제 리포트 생성.

    low_confidence=True 표기.
    """
    logger.warning("[force_report] 3차 실패 — 신뢰도 낮음 표기 후 강제 리포트 생성")
    result = state.get("llm_result", {})
    report = {
        **result,
        "low_confidence":  True,
        "retry_count":     state.get("retry_count", 0),
        "scenario_type":   state.get("scenario_type", "일반"),
        "rag_chunk_count": len(state.get("rag_chunks", [])),
    }
    return {**state, "report": report}


# ── 헬퍼 ─────────────────────────────────────────────────────────

def _search_rag(
    ticker: str,
    run_dir: Path,
    top_k: int,
    collection: str,
    store_strategy: str,
    store_params: dict,
) -> list[dict]:
    """벡터DB 검색 — embeddings.json에서 임베딩 전략을 자동 감지."""
    from src.pipeline.embedding.snapshot import exists as emb_exists, load as emb_load
    from src.pipeline.vectordb.store import search_similar
    from src.pipeline.rag.predictor import _model_to_strategy
    from src.pipeline.embedding.embedder import _registry as emb_registry

    query = f"{ticker} 주가 전망 실적 뉴스 공시"
    emb_path = run_dir / "embeddings.json"

    if not emb_exists(emb_path):
        logger.warning("[_search_rag] embeddings.json 없음 — RAG 스킵")
        return []

    embedded = emb_load(emb_path)
    if not embedded:
        return []

    emb_strategy = _model_to_strategy(embedded[0].model)
    registry     = emb_registry()

    if emb_strategy not in registry:
        logger.warning("[_search_rag] 임베딩 전략 '%s' 미인식 — RAG 스킵", emb_strategy)
        return []

    embedder     = registry[emb_strategy]()
    query_vector = embedder.embed([query])[0]

    results = search_similar(
        query_vector=query_vector,
        strategy=store_strategy,
        collection=collection,
        top_k=top_k,
        **store_params,
    )
    logger.info("[_search_rag] 검색 완료 — %d건", len(results))
    return [{"text": r.text, "source": r.source, "score": r.score} for r in results]
