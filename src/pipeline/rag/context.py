"""
벡터DB 검색 결과와 수집 데이터를 LLM 프롬프트용 컨텍스트 블록으로 변환.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 시나리오 타입 상수
SCENARIO_NORMAL = "일반"
SCENARIO_SHOCK_UP = "외부충격_상승"
SCENARIO_SHOCK_DOWN = "외부충격_하락"

# 외부충격 발동 임계값 (%)
_SHOCK_THRESHOLD = 3.0


def detect_scenario(collected_data: dict) -> str:
    """
    미국 반도체 지수 기반 시나리오 타입 결정 (Case C).

    SOX 지수 변동과 미국 파일럿 5종목 평균 변동이 모두 ±3% 이상이면
    외부충격 시나리오로 분류한다.

    Args:
        collected_data: 수집된 데이터 딕셔너리 (ticker → {change_pct, ...})

    Returns:
        시나리오 타입 문자열
    """
    us_tickers = ["NVDA", "AMD", "INTC", "AVGO", "QCOM"]
    sox_ticker = "^SOX"

    sox_change = _get_change_pct(collected_data, sox_ticker)
    us_changes = [_get_change_pct(collected_data, t) for t in us_tickers]
    us_avg = sum(us_changes) / len(us_changes) if us_changes else 0.0

    logger.debug("SOX 변동: %.2f%%  미국 평균 변동: %.2f%%", sox_change, us_avg)

    if abs(sox_change) >= _SHOCK_THRESHOLD and abs(us_avg) >= _SHOCK_THRESHOLD:
        scenario = SCENARIO_SHOCK_UP if sox_change > 0 else SCENARIO_SHOCK_DOWN
        logger.info("외부충격 감지 — %s (SOX %.2f%%, US avg %.2f%%)",
                    scenario, sox_change, us_avg)
        return scenario

    return SCENARIO_NORMAL


def _get_change_pct(data: dict, ticker: str) -> float:
    """ticker의 change_pct 값 반환. 없으면 0.0."""
    entry = data.get(ticker, {})
    if isinstance(entry, dict):
        return float(entry.get("change_pct", 0.0))
    return 0.0


def build_main_context(
    ticker: str,
    collected_data: dict,
    rag_chunks: list[dict],
) -> str:
    """
    메인 종목 컨텍스트 블록 구성.

    주가 OHLCV 요약 + 벡터DB RAG 검색 결과를 합쳐 문자열로 반환.
    """
    lines: list[str] = [f"## 메인 종목: {ticker}"]

    # 주가 데이터 요약
    price_data = collected_data.get(ticker, {})
    if price_data:
        lines.append(_format_price_summary(ticker, price_data))
    else:
        lines.append("(주가 데이터 없음)")

    # RAG 검색 결과
    if rag_chunks:
        lines.append("\n### 관련 문서 (벡터DB 검색 결과)")
        for i, chunk in enumerate(rag_chunks, 1):
            src = chunk.get("source", "")
            text = chunk.get("text", "")[:300]
            score = chunk.get("score", 0.0)
            lines.append(f"[{i}] (유사도 {score:.2f}) [{src}]\n{text}")
    else:
        lines.append("(관련 문서 없음)")

    return "\n".join(lines)


def build_domestic_context(collected_data: dict, domestic_tickers: list[str]) -> str:
    """국내 참고 종목 컨텍스트 블록 구성 (Case D)."""
    lines: list[str] = ["## 국내 참고 종목 동향"]
    for ticker in domestic_tickers:
        data = collected_data.get(ticker, {})
        if data:
            change = _get_change_pct(collected_data, ticker)
            name = data.get("name", ticker)
            volume = data.get("volume", "N/A")
            lines.append(f"- {name} ({ticker}): 등락 {change:+.2f}%  거래량 {volume}")
        else:
            lines.append(f"- {ticker}: (데이터 없음)")
    return "\n".join(lines)


def build_us_context(collected_data: dict, us_tickers: list[str], sox_ticker: str = "^SOX") -> str:
    """미국 참고 종목 및 SOX 지수 컨텍스트 블록 구성 (Case D)."""
    lines: list[str] = ["## 미국 반도체 동향"]

    sox_change = _get_change_pct(collected_data, sox_ticker)
    lines.append(f"- SOX 지수: {sox_change:+.2f}%")

    for ticker in us_tickers:
        change = _get_change_pct(collected_data, ticker)
        lines.append(f"- {ticker}: {change:+.2f}%")

    return "\n".join(lines)


def _format_price_summary(ticker: str, data: dict) -> str:
    """주가 데이터 딕셔너리를 읽기 좋은 텍스트로 변환."""
    if isinstance(data, list):
        # OHLCV 리스트 형태인 경우 최근 5일만
        recent = data[-5:] if len(data) > 5 else data
        rows = [f"  {row}" for row in recent]
        return "### 최근 주가 (OHLCV)\n" + "\n".join(rows)

    # 딕셔너리 형태
    lines = ["### 주가 요약"]
    for k, v in data.items():
        if k not in ("name",):
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def load_collected_data(run_dir: Path) -> dict:
    """
    run_dir 내 *.json 파일을 읽어 {ticker: data} 딕셔너리로 반환.

    loaded_docs.json / chunks.json / embeddings.json / vectordb_meta.json 은 제외.
    """
    _EXCLUDED = {"loaded_docs.json", "chunks.json", "embeddings.json", "vectordb_meta.json"}
    result: dict = {}
    for fpath in run_dir.glob("*.json"):
        if fpath.name in _EXCLUDED:
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            # 파일명 (확장자 제외)을 키로 사용
            key = fpath.stem
            result[key] = data
        except Exception as exc:
            logger.warning("수집 데이터 로드 실패: %s — %s", fpath.name, exc)
    return result
