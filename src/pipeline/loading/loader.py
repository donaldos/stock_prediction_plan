"""
data_loading 오케스트레이터.

수집된 run_dir 의 JSON 파일들을 읽어 텍스트 로딩을 수행하고
결과를 loaded_docs.json (스냅샷) 으로 저장한다.

스냅샷 캐시:
  - loaded_docs.json 이 이미 존재하면 재크롤링 없이 스냅샷을 반환한다.
  - force=True 로 강제 재크롤링 가능 (--force-load 플래그).

병렬 처리:
  - naver_news / dart_disclosure / pdf_files 로더를 ThreadPoolExecutor 로 동시 실행.
  - 각 로더는 독립적이므로 결과 충돌 없음.
"""

from __future__ import annotations
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

from . import snapshot as snap
from .url_loader import load_from_collected as _load_news
from .dart_doc_loader import load_from_collected as _load_dart
from .pdf_loader import load_from_collected as _load_pdf
from .models import Document


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_one(name: str, fn, *args, **kwargs) -> tuple[str, list[Document]]:
    """단일 로더 실행. (source_name, docs) 반환."""
    logger.info("로딩중 — %s", name)
    t0 = time.perf_counter()
    try:
        docs = fn(*args, **kwargs)
        elapsed = time.perf_counter() - t0
        logger.info("%s 로딩 완료 — %d건  elapsed=%.2fs", name, len(docs), elapsed)
        return name, docs
    except Exception as e:
        elapsed = time.perf_counter() - t0
        logger.error("%s 로딩 실패 — elapsed=%.2fs  error=%s", name, elapsed, e, exc_info=True)
        return name, []


def load_and_save(
    run_dir: Path,
    dart_api_key: str = "",
    pdf_engine: str = "pdfplumber",
    force: bool = False,
) -> Path:
    """
    run_dir 내 수집 JSON에서 텍스트를 병렬 로딩하고 loaded_docs.json 에 저장.

    naver_news / dart_disclosure / pdf_files 세 로더를 ThreadPoolExecutor 로
    동시 실행한다. 스냅샷이 이미 존재하면 재로딩 없이 경로를 반환한다.

    Args:
        run_dir:      collected_datas/{YYYY_MMDD_HH}/ 경로
        dart_api_key: DART API 키 (dart_disclosure 로딩에 필요)
        pdf_engine:   PDF 추출 엔진 (기본: pdfplumber)
        force:        True 이면 기존 스냅샷 무시하고 재로딩

    Returns:
        저장된 loaded_docs.json 경로
    """
    output_path = run_dir / "loaded_docs.json"

    # ── 스냅샷 캐시 확인 ────────────────────────────────────────
    if not force and snap.exists(output_path):
        logger.info("캐시 사용 — 기존 스냅샷 로드: %s", snap.summary(output_path))
        return output_path

    # ── 로더 작업 목록 구성 (JSON 읽기는 빠른 로컬 I/O → 순차) ──
    tasks: list[tuple[str, callable, list, dict]] = []

    news_json = _read_json(run_dir / "naver_news.json")
    if news_json:
        tasks.append(("naver_news", _load_news, [news_json.get("data", {})], {}))
    else:
        logger.warning("naver_news.json 없음 — 건너뜀")

    dart_json = _read_json(run_dir / "dart_disclosure.json")
    if dart_json and dart_api_key:
        tasks.append(("dart_disclosure", _load_dart,
                      [dart_json.get("data", {})], {"api_key": dart_api_key}))
    else:
        if not dart_api_key:
            logger.warning("dart_disclosure 건너뜀 — DART_API_KEY 미설정")
        else:
            logger.warning("dart_disclosure.json 없음 — 건너뜀")

    pdf_json = _read_json(run_dir / "pdf_files.json")
    if pdf_json:
        tasks.append(("pdf", _load_pdf,
                      [pdf_json.get("data", {})], {"engine": pdf_engine}))
    else:
        logger.warning("pdf_files.json 없음 — 건너뜀")

    # ── 병렬 로딩 ───────────────────────────────────────────────
    results: dict[str, list[Document]] = {}
    logger.info("로딩 시작 — 로더 %d개 병렬 실행", len(tasks))

    t_total = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(tasks) or 1) as pool:
        futures = {
            pool.submit(_load_one, name, fn, *args, **kwargs): name
            for name, fn, args, kwargs in tasks
        }
        for future in as_completed(futures):
            name, docs = future.result()
            results[name] = docs

    # ── 결과 병합 (순서 보장: news → dart → pdf) ────────────────
    all_docs: list[Document] = []
    counts: dict[str, int] = {}
    for name in ("naver_news", "dart_disclosure", "pdf"):
        docs = results.get(name, [])
        all_docs.extend(docs)
        counts[name] = len(docs)

    # ── 스냅샷 저장 ─────────────────────────────────────────────
    snap.save(
        documents=all_docs,
        path=output_path,
        meta={"run_dir": str(run_dir), "counts": counts},
    )

    logger.info("전체 로딩 완료 — total=%d  total_elapsed=%.2fs",
                len(all_docs), time.perf_counter() - t_total)
    return output_path


def load_snapshot(run_dir: Path) -> list[Document]:
    """
    run_dir 의 loaded_docs.json 스냅샷에서 Document 리스트 반환.
    청킹 등 다운스트림 단계에서 사용한다.

    Args:
        run_dir: collected_datas/{YYYY_MMDD_HH}/ 경로

    Returns:
        Document 리스트
    """
    return snap.load(run_dir / "loaded_docs.json")
