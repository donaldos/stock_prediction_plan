"""
수집 오케스트레이터.
data_sources.json 의 활성 소스를 ThreadPoolExecutor 로 병렬 실행하고,
결과를 collected_datas/{YYYY_MMDD_HH}/ 폴더에 소스별 JSON 파일로 저장한다.
"""

from __future__ import annotations
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .models import TickerConfig, DataSourceConfig

logger = logging.getLogger(__name__)
from .fetchers import (
    fetch_krx_ohlcv,
    fetch_krx_investor,
    fetch_us_price,
    fetch_sox_index,
    fetch_naver_news,
    fetch_dart_disclosure,
    fetch_dart_financial,
    fetch_pdf_files,
)

# 프로젝트 루트 기준 저장 경로
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_COLLECTED_DIR = _PROJECT_ROOT / "collected_datas"

# source id → fetcher 매핑
_DISPATCH: dict = {
    "krx_ohlcv":       lambda tc, params: fetch_krx_ohlcv(tc.active_kr(), params),
    "krx_investor":    lambda tc, params: fetch_krx_investor(tc.active_kr(), params),
    "us_price":        lambda tc, params: fetch_us_price(tc.active_us(), params),
    "sox_index":       lambda tc, params: fetch_sox_index(tc.active_index(), params),
    "naver_news":      lambda tc, params: fetch_naver_news(tc.active_kr(), params),
    "dart_disclosure": lambda tc, params: fetch_dart_disclosure(tc.active_kr(), params),
    "dart_financial":  lambda tc, params: fetch_dart_financial(tc.active_kr(), params),
    "pdf_files":       lambda tc, params: fetch_pdf_files(tc.active_kr(), params),
}


def _make_run_dir(base_dir: Path, now: datetime) -> Path:
    """collected_datas/YYYY_MMDD_HH 폴더 생성 후 반환."""
    folder = now.strftime("%Y_%m%d_%H")
    run_dir = base_dir / folder
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _fetch_one(
    source_id: str,
    fetcher,
    tickers: TickerConfig,
    params: dict,
    run_dir: Path,
    now: datetime,
) -> str:
    """단일 소스 수집 + 저장. 성공 시 source_id 반환, 실패 시 예외 전파."""
    logger.info("수집중 — source_id=%s", source_id)
    t0 = time.perf_counter()
    try:
        data = fetcher(tickers, params)
        _save_source(run_dir, source_id, data, now)
        elapsed = time.perf_counter() - t0
        logger.info("수집 완료 — source_id=%s  elapsed=%.2fs", source_id, elapsed)
    except Exception as e:
        elapsed = time.perf_counter() - t0
        logger.error("수집 실패 — source_id=%s  elapsed=%.2fs  error=%s",
                     source_id, elapsed, e, exc_info=True)
        _save_source(run_dir, source_id, {"error": str(e)}, now)
    return source_id


def collect_and_save(
    tickers: TickerConfig,
    sources: DataSourceConfig,
    base_dir: Path | None = None,
    max_workers: int = 5,
) -> Path:
    """
    활성 소스를 병렬 수집하고 날짜 폴더에 저장.

    각 소스는 ThreadPoolExecutor 를 통해 동시에 실행된다.
    소스별 결과 파일이 독립적이므로 파일 충돌 없음.

    Args:
        tickers:     TickerConfig (tickers.json 로드 결과)
        sources:     DataSourceConfig (data_sources.json 로드 결과)
        base_dir:    저장 루트 (기본값: collected_datas/)
        max_workers: 최대 병렬 스레드 수 (기본: 5)

    Returns:
        저장된 폴더 경로 (e.g. collected_datas/2026_0306_18/)
    """
    now = datetime.now()
    run_dir = _make_run_dir(base_dir or _COLLECTED_DIR, now)

    active = sources.active_sources()
    logger.info("수집 시작 — run_dir=%s  소스=%d개  workers=%d",
                run_dir, len(active), min(max_workers, len(active)))

    t_total = time.perf_counter()
    futures = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(active))) as pool:
        for source in active:
            fetcher = _DISPATCH.get(source.id)
            if fetcher is None:
                logger.warning("핸들러 없음, 건너뜀 — source_id=%s", source.id)
                continue
            future = pool.submit(
                _fetch_one, source.id, fetcher, tickers, source.params, run_dir, now
            )
            futures[future] = source.id

        for future in as_completed(futures):
            future.result()   # 예외가 있으면 여기서 다시 발생

    logger.info("전체 수집 완료 — 저장 위치=%s  total_elapsed=%.2fs",
                run_dir, time.perf_counter() - t_total)
    return run_dir


def _save_source(run_dir: Path, source_id: str, data: dict, collected_at: datetime) -> None:
    """단일 소스 결과를 {source_id}.json 으로 저장."""
    payload = {
        "source_id": source_id,
        "collected_at": collected_at.isoformat(),
        "data": data,
    }
    fpath = run_dir / f"{source_id}.json"
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
