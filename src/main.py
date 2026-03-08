"""
최상위 실행 진입점.

사용법 (stock_prediction_plan/ 폴더에서 실행):

  config 검증만:
    python3 -m src.main

  데이터 수집 (수집 데이터 있으면 자동 건너뜀):
    python3 -m src.main --collect

  데이터 수집 강제 재실행:
    python3 -m src.main --collect --force-collect

  텍스트 로딩 (스냅샷 있으면 자동 건너뜀):
    python3 -m src.main --load

  텍스트 로딩 강제 재실행:
    python3 -m src.main --load --force-load

  텍스트 로딩 폴더 지정:
    python3 -m src.main --load 2026_0306_19

  PDF 엔진 지정:
    python3 -m src.main --load --pdf-engine pymupdf

  청킹 (chunks.json 있으면 자동 건너뜀):
    python3 -m src.main --chunk

  청킹 전략 지정:
    python3 -m src.main --chunk --strategy recursive
    python3 -m src.main --chunk --strategy sentence
    python3 -m src.main --chunk --strategy token

  청킹 강제 재실행:
    python3 -m src.main --chunk --force-chunk

  임베딩 (embeddings.json 있으면 자동 건너뜀):
    python3 -m src.main --embed

  임베딩 전략 지정:
    python3 -m src.main --embed --embed-strategy bge
    python3 -m src.main --embed --embed-strategy upstage
    python3 -m src.main --embed --embed-strategy openai

  임베딩 강제 재실행:
    python3 -m src.main --embed --force-embed

  벡터DB 저장 (vectordb_meta.json 있으면 자동 건너뜀):
    python3 -m src.main --store

  벡터DB 전략 지정:
    python3 -m src.main --store --store-strategy chroma
    python3 -m src.main --store --store-strategy pinecone

  벡터DB 강제 재저장:
    python3 -m src.main --store --force-store

  RAG + LLM 예측 (prediction_result.json 있으면 자동 건너뜀):
    python3 -m src.main --predict

  LLM 전략 지정:
    python3 -m src.main --predict --llm-strategy claude
    python3 -m src.main --predict --llm-strategy openai

  예측 강제 재실행:
    python3 -m src.main --predict --force-predict

  LangGraph 오케스트레이션 (orchestration_result.json 있으면 자동 건너뜀):
    python3 -m src.main --orchestrate

  오케스트레이션 LLM 전략 지정:
    python3 -m src.main --orchestrate --llm-strategy claude
    python3 -m src.main --orchestrate --llm-strategy openai

  오케스트레이션 강제 재실행:
    python3 -m src.main --orchestrate --force-orchestrate

  Slack 리포트 발송 (orchestration_result.json → Slack):
    python3 -m src.main --notify

  수집 + 로딩 + 청킹 + 임베딩 + 벡터DB 저장 전체 파이프라인:
    python3 -m src.main --all

  전체 강제 재실행:
    python3 -m src.main --all --force-collect --force-load --force-chunk --force-embed --force-store --force-predict --force-orchestrate
"""

from __future__ import annotations
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.logger import setup_logging

logger = logging.getLogger(__name__)

# ── 경로 상수 ──────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_COLLECTED_DIR = _PROJECT_ROOT / "collected_datas"

# 수집 완료 판정에 필요한 최소 소스 파일 수
_MIN_SOURCE_FILES = 3


# ── 인자 파싱 유틸 ─────────────────────────────────────────────

def _get_flag(flag: str) -> bool:
    return flag in sys.argv


def _has_option(option: str) -> bool:
    """--option 이 실제로 CLI에 명시되었는지 여부 (override 감지용)."""
    return option in sys.argv


def _get_option(option: str, default: str = "") -> str:
    """--option value 형태의 값 반환."""
    try:
        idx = sys.argv.index(option)
        val = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        return val if val and not val.startswith("--") else default
    except ValueError:
        return default


# ── 폴더 유틸 ─────────────────────────────────────────────────

def _current_run_dir() -> Path:
    """현재 시각 기준 run_dir 경로 반환 (생성하지 않음)."""
    folder = datetime.now().strftime("%Y_%m%d_%H")
    return _COLLECTED_DIR / folder


def _find_latest_run_dir() -> Path | None:
    """collected_datas/ 에서 가장 최근 YYYY_MMDD_HH 폴더 반환."""
    if not _COLLECTED_DIR.exists():
        return None
    candidates = sorted(
        [d for d in _COLLECTED_DIR.iterdir() if d.is_dir()
         if not d.name.startswith("pdf")],      # pdf_datas 제외
        key=lambda d: d.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _has_collected_data(run_dir: Path) -> bool:
    """
    run_dir 에 수집 결과 파일이 충분히 있는지 확인.
    loaded_docs.json 을 제외한 *.json 파일이 _MIN_SOURCE_FILES 개 이상이면 True.
    """
    if not run_dir.exists():
        return False
    source_files = [
        f for f in run_dir.glob("*.json")
        if f.name != "loaded_docs.json"
    ]
    return len(source_files) >= _MIN_SOURCE_FILES


# ── 단계별 실행 함수 ───────────────────────────────────────────

def _log_config() -> tuple:
    """config 내용을 INFO 로그로 출력. (tickers, sources) 반환."""
    from src.pipeline.collection.config_loader import load_all

    tickers, sources = load_all()

    logger.info("=== tickers.json ===")
    sections = {
        "main":               tickers.main,
        "domestic_reference": tickers.domestic_reference,
        "us_reference":       tickers.us_reference,
        "us_index":           tickers.us_index,
    }
    for section, items in sections.items():
        for t in items:
            logger.info("[%s] %s  %s (%s)%s",
                        section, t.ticker, t.name, t.market,
                        f"  ※{t.note}" if t.note else "")

    logger.info("활성 국내=%s 미국=%s 지수=%s",
                [t.ticker for t in tickers.active_kr()],
                [t.ticker for t in tickers.active_us()],
                [t.ticker for t in tickers.active_index()])

    logger.info("=== data_sources.json ===")
    logger.info("재시도 정책 — 최대 %d회 / %d초 간격 / 최종실패→%s",
                sources.retry_policy.max_retries,
                sources.retry_policy.interval_seconds,
                sources.retry_policy.on_final_failure)
    for s in sources.sources:
        clean_params = {k: v for k, v in s.params.items() if k != "note"} if s.params else {}
        logger.info("[%s] %s  library=%s  schedule=%s  params=%s",
                    "활성" if s.active else "비활성", s.id,
                    s.library, s.schedule, clean_params)

    logger.info("활성 소스 id=%s", [s.id for s in sources.active_sources()])
    return tickers, sources


def _run_collect(force: bool = False) -> Path:
    """
    데이터 수집 실행 → run_dir 반환.

    현재 시간대 폴더에 수집 파일이 이미 있으면 건너뛴다.
    force=True 이면 기존 데이터가 있어도 재수집한다.
    """
    logger.info("=== 수집 단계 시작%s ===", "  (강제 재수집)" if force else "")
    run_dir = _current_run_dir()

    if not force and _has_collected_data(run_dir):
        source_files = sorted(
            f.name for f in run_dir.glob("*.json")
            if f.name not in ("loaded_docs.json", "chunks.json")
        )
        logger.info("캐시 사용 — 수집 건너뜀: folder=%s files=%s",
                    run_dir.name, source_files)
        return run_dir

    from src.pipeline.collection.config_loader import load_all
    from src.pipeline.collection.collector import collect_and_save

    tickers, sources = load_all()
    run_dir = collect_and_save(tickers, sources)
    return run_dir


def _run_load(
    run_dir: Path,
    pdf_engine: str = "pdfplumber",
    force: bool = False,
) -> None:
    """텍스트 로딩 실행."""
    from src.pipeline.loading.loader import load_and_save
    from src.pipeline.loading import snapshot as snap_mod

    dart_api_key = ""
    try:
        from src.settings import get_dart_api_key
        dart_api_key = get_dart_api_key()
    except Exception:
        logger.warning("DART_API_KEY 미설정 — dart_disclosure 로딩 스킵")

    logger.info("=== 로딩 단계 시작: folder=%s%s ===",
                run_dir.name, "  (강제 재로딩)" if force else "")
    output = load_and_save(
        run_dir,
        dart_api_key=dart_api_key,
        pdf_engine=pdf_engine,
        force=force,
    )
    logger.info("로딩 단계 완료 — %s  저장=%s", snap_mod.summary(output), output)


def _run_chunk(
    run_dir: Path,
    strategy: str = "recursive",
    force: bool = False,
    strategy_params: dict | None = None,
) -> None:
    """청킹 실행."""
    from src.pipeline.chunking.chunker import chunk_and_save

    params = strategy_params or {}
    logger.info("=== 청킹 단계 시작: strategy=%s params=%s folder=%s%s ===",
                strategy, params, run_dir.name, "  (강제 재청킹)" if force else "")
    output = chunk_and_save(run_dir, strategy=strategy, force=force, **params)

    with open(output, encoding="utf-8") as f:
        result = json.load(f)
    logger.info("청킹 단계 완료 — total=%d counts=%s  저장=%s",
                result.get("total", 0), result.get("counts", {}), output)


def _run_embed(
    run_dir: Path,
    strategy: str = "bge",
    force: bool = False,
    strategy_params: dict | None = None,
) -> None:
    """임베딩 실행."""
    from src.pipeline.embedding.embedder import embed_and_save
    from src.pipeline.embedding import snapshot as emb_snap

    params = strategy_params or {}
    logger.info("=== 임베딩 단계 시작: strategy=%s params=%s folder=%s%s ===",
                strategy, params, run_dir.name, "  (강제 재임베딩)" if force else "")
    output = embed_and_save(run_dir, strategy=strategy, force=force, **params)
    logger.info("임베딩 단계 완료 — %s  저장=%s", emb_snap.summary(output), output)


def _run_predict(
    run_dir: Path,
    llm_strategy: str = "claude",
    ticker: str = "005930",
    collection: str = "stock_rag",
    store_strategy: str = "chroma",
    store_params: dict | None = None,
    top_k: int = 5,
    top_k_expanded: int = 10,
    force: bool = False,
    strategy_params: dict | None = None,
) -> None:
    """RAG + LLM 예측 실행."""
    from src.pipeline.rag.predictor import predict_and_save
    from src.pipeline.rag import snapshot as rag_snap

    params = strategy_params or {}
    logger.info(
        "=== RAG 예측 단계 시작: llm=%s  ticker=%s  collection=%s  folder=%s%s ===",
        llm_strategy, ticker, collection, run_dir.name, "  (강제 재예측)" if force else "",
    )
    output = predict_and_save(
        run_dir=run_dir,
        ticker=ticker,
        strategy=llm_strategy,
        force=force,
        collection=collection,
        store_strategy=store_strategy,
        top_k=top_k,
        top_k_expanded=top_k_expanded,
        store_params=store_params or {},
        **params,
    )
    logger.info("RAG 예측 단계 완료 — %s  저장=%s", rag_snap.summary(output), output)


def _run_orchestrate(
    run_dir: Path,
    llm_strategy: str = "claude",
    ticker: str = "005930",
    collection: str = "stock_rag",
    store_strategy: str = "chroma",
    store_params: dict | None = None,
    top_k: int = 5,
    top_k_expanded: int = 10,
    force: bool = False,
    strategy_params: dict | None = None,
) -> None:
    """LangGraph 오케스트레이션 실행."""
    from src.pipeline.orchestration.runner import run_and_save
    from src.pipeline.orchestration import snapshot as orch_snap

    params = strategy_params or {}
    logger.info(
        "=== 오케스트레이션 단계 시작: llm=%s  ticker=%s  folder=%s%s ===",
        llm_strategy, ticker, run_dir.name, "  (강제 재실행)" if force else "",
    )
    output = run_and_save(
        run_dir=run_dir,
        ticker=ticker,
        llm_strategy=llm_strategy,
        force=force,
        llm_params=params,
        collection=collection,
        store_strategy=store_strategy,
        store_params=store_params or {},
        top_k=top_k,
        top_k_expanded=top_k_expanded,
    )
    logger.info("오케스트레이션 완료 — %s  저장=%s", orch_snap.summary(output), output)


def _run_notify(run_dir: Path) -> None:
    """orchestration_result.json → Slack Block Kit 리포트 발송."""
    from src.pipeline.notification.slack import send_from_result_file
    from src.settings import get_slack_webhook_url

    result_path = run_dir / "orchestration_result.json"
    if not result_path.exists():
        logger.error("orchestration_result.json 없음: %s  먼저 --orchestrate 실행 필요", run_dir)
        return

    webhook_url = get_slack_webhook_url()
    logger.info("=== Slack 발송 단계 시작: folder=%s ===", run_dir.name)
    send_from_result_file(result_path, webhook_url)
    logger.info("Slack 발송 완료")


def _run_store(
    run_dir: Path,
    strategy: str = "chroma",
    collection: str = "stock_rag",
    force: bool = False,
    strategy_params: dict | None = None,
) -> None:
    """벡터DB upsert 실행."""
    from src.pipeline.vectordb.store import upsert_and_save
    from src.pipeline.vectordb import snapshot as vdb_snap

    params = strategy_params or {}
    output = run_dir / "vectordb_meta.json"
    logger.info("=== 벡터DB 저장 단계 시작: strategy=%s collection=%s params=%s folder=%s%s ===",
                strategy, collection, params, run_dir.name, "  (강제 재저장)" if force else "")
    upsert_and_save(run_dir, strategy=strategy, collection=collection, force=force, **params)
    logger.info("벡터DB 저장 단계 완료 — %s  저장=%s", vdb_snap.summary(output), output)


# ── main ───────────────────────────────────────────────────────

def main() -> None:
    do_collect      = _get_flag("--collect")
    do_load         = _get_flag("--load")
    do_chunk        = _get_flag("--chunk")
    do_embed        = _get_flag("--embed")
    do_store        = _get_flag("--store")
    do_predict      = _get_flag("--predict")
    do_orchestrate  = _get_flag("--orchestrate")
    do_notify       = _get_flag("--notify")
    do_all          = _get_flag("--all")
    force_collect   = _get_flag("--force-collect")
    force_load      = _get_flag("--force-load")
    force_chunk     = _get_flag("--force-chunk")
    force_embed     = _get_flag("--force-embed")
    force_store     = _get_flag("--force-store")
    force_predict   = _get_flag("--force-predict")
    force_orchestrate = _get_flag("--force-orchestrate")
    debug          = _get_flag("--debug")
    load_folder    = _get_option("--load", default="")

    setup_logging(level=logging.DEBUG if debug else logging.INFO)
    logger.info("파이프라인 시작 — args=%s", sys.argv[1:])

    # ── pipeline.json 로드 → CLI override 적용 ────────────────
    from src.pipeline.collection.config_loader import load_pipeline_config
    pipeline_cfg = load_pipeline_config()
    logger.info(
        "pipeline.json 로드 — pdf_engine=%s  chunk=%s%s  embed=%s%s  vectordb=%s@%s",
        pipeline_cfg.pdf_engine,
        pipeline_cfg.chunk_strategy, pipeline_cfg.chunk_params,
        pipeline_cfg.embed_strategy, pipeline_cfg.embed_params,
        pipeline_cfg.vectordb_strategy, pipeline_cfg.vectordb_collection,
    )

    pdf_engine      = _get_option("--pdf-engine",      default="") or pipeline_cfg.pdf_engine
    chunk_strategy  = _get_option("--strategy",        default="") or pipeline_cfg.chunk_strategy
    embed_strategy  = _get_option("--embed-strategy",  default="") or pipeline_cfg.embed_strategy
    store_strategy  = _get_option("--store-strategy",  default="") or pipeline_cfg.vectordb_strategy
    llm_strategy    = _get_option("--llm-strategy",    default="") or pipeline_cfg.llm_strategy

    # CLI override 시 해당 전략의 params 를 config에서 선택
    chunk_params  = pipeline_cfg.chunk_params_for(chunk_strategy)
    embed_params  = pipeline_cfg.embed_params_for(embed_strategy)
    store_params  = pipeline_cfg.vectordb_params_for(store_strategy)
    llm_params    = pipeline_cfg.llm_params_for(llm_strategy)

    if _has_option("--pdf-engine"):
        logger.info("pdf_engine override — CLI: %s", pdf_engine)
    if _has_option("--strategy"):
        logger.info("chunk_strategy override — CLI: %s  params=%s", chunk_strategy, chunk_params)
    if _has_option("--embed-strategy"):
        logger.info("embed_strategy override — CLI: %s  params=%s", embed_strategy, embed_params)
    if _has_option("--store-strategy"):
        logger.info("store_strategy override — CLI: %s  params=%s", store_strategy, store_params)
    if _has_option("--llm-strategy"):
        logger.info("llm_strategy override — CLI: %s  params=%s", llm_strategy, llm_params)

    _log_config()

    run_dir: Path | None = None

    # ── 수집 ──────────────────────────────────────────────────
    if do_collect or do_all:
        run_dir = _run_collect(force=force_collect)

    # ── 로딩 ──────────────────────────────────────────────────
    if do_load or do_all:
        if load_folder:
            run_dir = _COLLECTED_DIR / load_folder
            if not run_dir.exists():
                logger.error("폴더 없음: %s", run_dir)
                sys.exit(1)
        elif run_dir is None:
            run_dir = _find_latest_run_dir()
            if run_dir is None:
                logger.error("collected_datas/ 에 수집 폴더 없음. 먼저 --collect 실행 필요")
                sys.exit(1)
            logger.info("최신 수집 폴더 사용: %s", run_dir.name)

        _run_load(run_dir, pdf_engine=pdf_engine, force=force_load)

    # ── 청킹 ──────────────────────────────────────────────────
    if do_chunk or do_all:
        if run_dir is None:
            run_dir = _find_latest_run_dir()
            if run_dir is None:
                logger.error("collected_datas/ 에 수집 폴더 없음")
                sys.exit(1)
            logger.info("최신 수집 폴더 사용: %s", run_dir.name)

        _run_chunk(run_dir, strategy=chunk_strategy, force=force_chunk, strategy_params=chunk_params)

    # ── 임베딩 ────────────────────────────────────────────────
    if do_embed or do_all:
        if run_dir is None:
            run_dir = _find_latest_run_dir()
            if run_dir is None:
                logger.error("collected_datas/ 에 수집 폴더 없음")
                sys.exit(1)
            logger.info("최신 수집 폴더 사용: %s", run_dir.name)

        _run_embed(run_dir, strategy=embed_strategy, force=force_embed, strategy_params=embed_params)

    # ── 벡터DB 저장 ───────────────────────────────────────────
    if do_store or do_all:
        if run_dir is None:
            run_dir = _find_latest_run_dir()
            if run_dir is None:
                logger.error("collected_datas/ 에 수집 폴더 없음")
                sys.exit(1)
            logger.info("최신 수집 폴더 사용: %s", run_dir.name)

        _run_store(
            run_dir,
            strategy=store_strategy,
            collection=pipeline_cfg.vectordb_collection,
            force=force_store,
            strategy_params=store_params,
        )

    # ── RAG + LLM 예측 ───────────────────────────────────────
    if do_predict or do_all:
        if run_dir is None:
            run_dir = _find_latest_run_dir()
            if run_dir is None:
                logger.error("collected_datas/ 에 수집 폴더 없음")
                sys.exit(1)
            logger.info("최신 수집 폴더 사용: %s", run_dir.name)

        _run_predict(
            run_dir,
            llm_strategy=llm_strategy,
            ticker=pipeline_cfg.llm_ticker,
            collection=pipeline_cfg.vectordb_collection,
            store_strategy=store_strategy,
            store_params=store_params,
            top_k=pipeline_cfg.search_top_k,
            top_k_expanded=pipeline_cfg.search_top_k_expanded,
            force=force_predict,
            strategy_params=llm_params,
        )

    # ── LangGraph 오케스트레이션 ──────────────────────────────
    if do_orchestrate or do_all:
        if run_dir is None:
            run_dir = _find_latest_run_dir()
            if run_dir is None:
                logger.error("collected_datas/ 에 수집 폴더 없음")
                sys.exit(1)
            logger.info("최신 수집 폴더 사용: %s", run_dir.name)

        _run_orchestrate(
            run_dir,
            llm_strategy=llm_strategy,
            ticker=pipeline_cfg.llm_ticker,
            collection=pipeline_cfg.vectordb_collection,
            store_strategy=store_strategy,
            store_params=store_params,
            top_k=pipeline_cfg.search_top_k,
            top_k_expanded=pipeline_cfg.search_top_k_expanded,
            force=force_orchestrate,
            strategy_params=llm_params,
        )

    # ── Slack 발송 ────────────────────────────────────────────
    if do_notify or do_all:
        if run_dir is None:
            run_dir = _find_latest_run_dir()
            if run_dir is None:
                logger.error("collected_datas/ 에 수집 폴더 없음")
                sys.exit(1)
            logger.info("최신 수집 폴더 사용: %s", run_dir.name)

        _run_notify(run_dir)

    logger.info("파이프라인 종료")


if __name__ == "__main__":
    main()
