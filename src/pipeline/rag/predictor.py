"""
RAG 기반 LLM 예측 파이프라인.

실행 흐름:
  1. 벡터DB에서 관련 청크 검색 (RAG)
  2. 컨텍스트 블록 구성 (main / domestic / US)
  3. LLM 예측 요청
  4. Case B: 신뢰도 검증 → 실패 시 최대 3회 재시도
  5. 결과 스냅샷 저장
"""
from __future__ import annotations

import logging
from datetime import date as _date
from pathlib import Path

from src.pipeline.rag.base import LLMStrategy
from src.pipeline.rag.models import PredictionOutput
from src.pipeline.rag.context import (
    detect_scenario,
    build_main_context,
    build_domestic_context,
    build_us_context,
    load_collected_data,
)
from src.pipeline.rag.prompt import build_messages
from src.pipeline.rag import snapshot as snap_mod

logger = logging.getLogger(__name__)

# 전략 레지스트리
_STRATEGY_REGISTRY: dict[str, type[LLMStrategy]] = {}

def _registry() -> dict[str, type[LLMStrategy]]:
    """지연 임포트로 전략 클래스 등록."""
    global _STRATEGY_REGISTRY
    if not _STRATEGY_REGISTRY:
        from src.pipeline.rag.strategies.claude import ClaudeStrategy
        from src.pipeline.rag.strategies.openai import OpenAILLMStrategy
        from src.pipeline.rag.strategies.gemini import GeminiStrategy
        _STRATEGY_REGISTRY = {
            "claude":  ClaudeStrategy,
            "openai":  OpenAILLMStrategy,
            "gemini":  GeminiStrategy,
        }
    return _STRATEGY_REGISTRY

# Case B 신뢰도 검증 기준
_MIN_CONFIDENCE = 7
_MIN_EVIDENCE = 3
_MAX_RETRIES = 3


class Predictor:
    """RAG + LLM 예측 실행기."""

    def __init__(self, strategy: LLMStrategy):
        self._strategy = strategy

    def run(
        self,
        ticker: str,
        run_dir: Path,
        top_k: int = 5,
        top_k_expanded: int = 10,
        collection: str = "stock_rag",
        store_strategy: str = "chroma",
        store_params: dict | None = None,
        domestic_tickers: list[str] | None = None,
        us_tickers: list[str] | None = None,
        target_date: str | None = None,
    ) -> PredictionOutput:
        """
        전체 RAG 예측 파이프라인 실행.

        Args:
            ticker:           예측 대상 종목코드
            run_dir:          수집 데이터 폴더
            top_k:            기본 RAG 검색 수
            top_k_expanded:   재시도 시 확장 검색 수
            collection:       벡터DB 컬렉션명
            store_strategy:   벡터DB 전략
            store_params:     벡터DB 전략 파라미터
            domestic_tickers: 국내 참고 종목 목록
            us_tickers:       미국 참고 종목 목록
            target_date:      예측 기준 날짜 (기본값: 오늘)

        Returns:
            PredictionOutput
        """
        target_date = target_date or str(_date.today())
        domestic_tickers = domestic_tickers or ["042700", "TBD", "000660"]
        us_tickers = us_tickers or ["NVDA", "AMD", "INTC", "AVGO", "QCOM"]
        store_params = store_params or {}

        # 수집 데이터 로드 (Case C, D 컨텍스트 구성용)
        collected_data = load_collected_data(run_dir)

        # Case C: 시나리오 감지
        scenario_type = detect_scenario(collected_data)
        logger.info("시나리오 감지: %s", scenario_type)

        # 국내 / 미국 컨텍스트 구성 (Case D)
        domestic_ctx = build_domestic_context(collected_data, domestic_tickers)
        us_ctx = build_us_context(collected_data, us_tickers)

        # 재시도 루프 (Case B)
        result: PredictionOutput | None = None
        use_few_shot = False
        current_top_k = top_k

        for attempt in range(1, _MAX_RETRIES + 2):  # 0차 + 최대 3회 재시도
            is_retry = attempt > 1
            logger.info(
                "LLM 예측 시도 %d/%d — top_k=%d  few_shot=%s",
                attempt, _MAX_RETRIES + 1, current_top_k, use_few_shot,
            )

            # RAG: 벡터DB에서 관련 청크 검색
            rag_chunks = self._search_rag(
                ticker=ticker,
                run_dir=run_dir,
                top_k=current_top_k,
                collection=collection,
                store_strategy=store_strategy,
                store_params=store_params,
            )

            # 메인 컨텍스트 구성
            main_ctx = build_main_context(ticker, collected_data, rag_chunks)

            # 프롬프트 구성
            messages = build_messages(
                ticker=ticker,
                date=target_date,
                main_context=main_ctx,
                domestic_context=domestic_ctx,
                us_context=us_ctx,
                scenario_type=scenario_type,
                use_few_shot=use_few_shot,
            )

            try:
                result = self._strategy.predict(messages)
                result.scenario_type = scenario_type  # 일관성 보장
            except Exception as exc:
                logger.error("LLM 호출 실패 (시도 %d): %s", attempt, exc)
                if attempt > _MAX_RETRIES:
                    raise
                current_top_k = top_k_expanded
                continue

            # Case B: 신뢰도 검증
            if _is_valid(result):
                logger.info(
                    "신뢰도 검증 통과 — confidence=%d  evidence=%d",
                    result.confidence_score, result.evidence_count,
                )
                break

            logger.warning(
                "신뢰도 검증 실패 (시도 %d) — confidence=%d (기준≥%d)  evidence=%d (기준≥%d)",
                attempt, result.confidence_score, _MIN_CONFIDENCE,
                result.evidence_count, _MIN_EVIDENCE,
            )

            if attempt == 1:
                # 1차 재시도: Top-K 확장
                current_top_k = top_k_expanded
            elif attempt == 2:
                # 2차 재시도: Few-shot 추가
                use_few_shot = True
            else:
                # 3차 실패: 강제 리포트 생성
                logger.warning("3차 재시도 실패 — 신뢰도 낮음 표기 후 강제 생성")
                result.low_confidence = True
                break

        if result is None:
            raise RuntimeError("예측 결과 생성 실패")

        return result

    def _search_rag(
        self,
        ticker: str,
        run_dir: Path,
        top_k: int,
        collection: str,
        store_strategy: str,
        store_params: dict,
    ) -> list[dict]:
        """
        쿼리 텍스트를 임베딩한 뒤 벡터DB에서 유사 청크를 검색.

        Returns:
            [{"text": ..., "source": ..., "score": ...}, ...]
        """
        query = f"{ticker} 주가 전망 실적 뉴스 공시"

        try:
            from src.pipeline.embedding.embedder import embed_and_save
            from src.pipeline.embedding.snapshot import exists as emb_exists, load as emb_load
            from src.pipeline.vectordb.store import search_similar

            # 임베딩 스냅샷에서 현재 전략 파악
            emb_path = run_dir / "embeddings.json"
            if not emb_exists(emb_path):
                logger.warning("embeddings.json 없음 — RAG 검색 스킵")
                return []

            embedded = emb_load(emb_path)
            if not embedded:
                return []

            # 쿼리 임베딩 (첫 번째 청크의 전략을 재사용)
            from src.pipeline.embedding.embedder import _registry as emb_registry
            model_name = embedded[0].model if embedded else "bge"
            # 전략 이름 추출: model_name 기반 매핑
            emb_strategy = _model_to_strategy(model_name)

            registry = emb_registry()
            if emb_strategy not in registry:
                logger.warning("임베딩 전략 '%s' 미인식 — RAG 스킵", emb_strategy)
                return []

            embedder_cls = registry[emb_strategy]
            embedder = embedder_cls()
            query_vector = embedder.embed([query])[0]

            results = search_similar(
                query_vector=query_vector,
                strategy=store_strategy,
                collection=collection,
                top_k=top_k,
                **store_params,
            )
            logger.info("RAG 검색 완료 — top_k=%d  결과=%d건", top_k, len(results))
            return [
                {"text": r.text, "source": r.source, "score": r.score}
                for r in results
            ]
        except Exception as exc:
            logger.warning("RAG 검색 실패 (건너뜀): %s", exc)
            return []


def _is_valid(result: PredictionOutput) -> bool:
    """Case B 신뢰도 검증."""
    score_ok    = result.confidence_score >= _MIN_CONFIDENCE
    evidence_ok = result.evidence_count >= _MIN_EVIDENCE
    return score_ok and evidence_ok


def _model_to_strategy(model_name: str) -> str:
    """임베딩 모델명 → 전략 이름 매핑."""
    model_lower = model_name.lower()
    if "bge" in model_lower:
        return "bge"
    if "upstage" in model_lower or "solar" in model_lower:
        return "upstage"
    if "text-embedding" in model_lower or "openai" in model_lower:
        return "openai"
    return "bge"  # 기본값


def predict_and_save(
    run_dir: Path,
    ticker: str,
    strategy: str = "claude",
    force: bool = False,
    collection: str = "stock_rag",
    store_strategy: str = "chroma",
    top_k: int = 5,
    top_k_expanded: int = 10,
    target_date: str | None = None,
    **strategy_kwargs,
) -> Path:
    """
    예측 실행 후 prediction_result.json 저장.

    이미 스냅샷이 있으면 건너뜀 (force=True 시 재실행).

    Returns:
        저장된 파일 경로
    """
    output_path = snap_mod.default_path(run_dir)

    if not force and snap_mod.exists(output_path):
        logger.info("캐시 사용 — 예측 건너뜀: %s", output_path.name)
        return output_path

    registry = _registry()
    if strategy not in registry:
        raise ValueError(
            f"알 수 없는 LLM 전략: '{strategy}'. 사용 가능: {list(registry)}"
        )

    # 벡터DB 파라미터는 별도 추출 (search_similar에 전달)
    store_params = strategy_kwargs.pop("store_params", {})

    llm = registry[strategy](**strategy_kwargs)
    predictor = Predictor(llm)

    result = predictor.run(
        ticker=ticker,
        run_dir=run_dir,
        top_k=top_k,
        top_k_expanded=top_k_expanded,
        collection=collection,
        store_strategy=store_strategy,
        store_params=store_params,
        target_date=target_date,
    )

    snap_mod.save(
        result,
        output_path,
        meta={
            "llm_strategy": strategy,
            "model_name":   llm.model_name,
            "ticker":       ticker,
        },
    )
    return output_path


def load_prediction(run_dir: Path) -> PredictionOutput:
    """저장된 prediction_result.json 로드."""
    return snap_mod.load(snap_mod.default_path(run_dir))
