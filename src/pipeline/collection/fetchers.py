"""
소스별 실제 데이터 수집 함수 모음.
각 함수는 Ticker 리스트와 params dict를 받아 수집 결과 dict를 반환한다.
"""

from __future__ import annotations
import io
import time
import warnings
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

from .models import Ticker

warnings.filterwarnings("ignore")

# 프로젝트 루트 (fetchers.py 기준 두 단계 상위)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# ──────────────────────────────────────────
# DART 공통 유틸
# ──────────────────────────────────────────

_DART_CORP_CODE_CACHE: dict[str, str] | None = None  # {stock_code(KRX ticker): corp_code}


def _fetch_dart_corp_codes(api_key: str) -> dict[str, str]:
    """
    DART corp_code ZIP 다운로드 → {stock_code: corp_code} 매핑 반환.
    프로세스 내에서 최초 1회만 다운로드하고 이후 캐시 반환.
    """
    global _DART_CORP_CODE_CACHE
    if _DART_CORP_CODE_CACHE is not None:
        return _DART_CORP_CODE_CACHE

    import requests
    resp = requests.get(
        "https://opendart.fss.or.kr/api/corpCode.xml",
        params={"crtfc_key": api_key},
        timeout=30,
    )
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        with zf.open("CORPCODE.xml") as xml_file:
            tree = ET.parse(xml_file)

    mapping: dict[str, str] = {}
    for item in tree.getroot().findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        corp_code = (item.findtext("corp_code") or "").strip()
        if stock_code:
            mapping[stock_code] = corp_code

    _DART_CORP_CODE_CACHE = mapping
    return mapping


# ──────────────────────────────────────────
# 국내 주가 OHLCV  (FinanceDataReader / pykrx fallback)
# ──────────────────────────────────────────

def fetch_krx_ohlcv(tickers: list[Ticker], params: dict) -> dict:
    """
    국내 종목 OHLCV 수집.

    Returns:
        {ticker: {"name": str, "market": str, "data": [{"Date":..., "Open":..., ...}]}}
    """
    try:
        import FinanceDataReader as fdr
    except ImportError as e:
        raise ImportError("pip install finance-datareader") from e

    lookback = params.get("lookback_days", 30)
    end = date.today()
    start = end - timedelta(days=lookback)
    results = {}

    for t in tickers:
        try:
            df = fdr.DataReader(t.ticker, start=str(start), end=str(end))
            df.index = df.index.astype(str)
            results[t.ticker] = {
                "name": t.name,
                "market": t.market,
                "data": df.reset_index().to_dict(orient="records"),
            }
        except Exception as e:
            results[t.ticker] = {"name": t.name, "market": t.market, "error": str(e)}

    return results


# ──────────────────────────────────────────
# 미국 주가 (yfinance)
# ──────────────────────────────────────────

def fetch_us_price(tickers: list[Ticker], params: dict) -> dict:
    """
    미국 종목 전일 종가 + 등락률 수집.

    Returns:
        {ticker: {"name": str, "close": float, "change_pct": float}}
    """
    try:
        import yfinance as yf
    except ImportError as e:
        raise ImportError("pip install yfinance") from e

    period = params.get("period", "2d")
    results = {}

    for t in tickers:
        try:
            hist = yf.Ticker(t.ticker).history(period=period)
            if len(hist) < 2:
                raise ValueError("데이터 부족 (2일치 미만)")
            latest = hist.iloc[-1]
            prev = hist.iloc[-2]
            change_pct = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100
            results[t.ticker] = {
                "name": t.name,
                "market": t.market,
                "close": round(float(latest["Close"]), 4),
                "change_pct": round(change_pct, 2),
                "date": str(hist.index[-1].date()),
            }
        except Exception as e:
            results[t.ticker] = {"name": t.name, "market": t.market, "error": str(e)}

    return results


# ──────────────────────────────────────────
# SOX 지수 (yfinance)
# ──────────────────────────────────────────

def fetch_sox_index(tickers: list[Ticker], params: dict) -> dict:
    """
    SOX 지수 전일 등락률 수집. (fetch_us_price 와 동일 로직)
    """
    return fetch_us_price(tickers, params)


# ──────────────────────────────────────────
# 네이버 금융 뉴스 (BeautifulSoup)
# ──────────────────────────────────────────

def fetch_naver_news(tickers: list[Ticker], params: dict) -> dict:
    """
    네이버 금융 종목별 뉴스 제목 + URL 수집.

    Returns:
        {ticker: {"name": str, "articles": [{"title": str, "url": str, "date": str}]}}
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise ImportError("pip install requests beautifulsoup4") from e

    max_articles = params.get("max_articles", 20)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://finance.naver.com",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    results = {}

    for t in tickers:
        url = f"https://finance.naver.com/item/news_news.nhn?code={t.ticker}&page=1"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            # 네이버 금융은 EUC-KR 인코딩 → bytes를 직접 전달해 명시적으로 지정
            soup = BeautifulSoup(resp.content, "html.parser", from_encoding="euc-kr")

            articles = []
            for row in soup.select("table.type5 tr"):
                a_tag = row.select_one("td.title a")
                date_tag = row.select_one("td.date")
                if not a_tag:
                    continue
                href = a_tag.get("href", "")
                full_url = f"https://finance.naver.com{href}" if href.startswith("/") else href
                articles.append({
                    "title": a_tag.get_text(strip=True),
                    "url": full_url,
                    "date": date_tag.get_text(strip=True) if date_tag else "",
                })
                if len(articles) >= max_articles:
                    break

            results[t.ticker] = {"name": t.name, "articles": articles}
            time.sleep(0.3)  # 네이버 크롤링 부하 방지

        except Exception as e:
            results[t.ticker] = {"name": t.name, "articles": [], "error": str(e)}

    return results


# ──────────────────────────────────────────
# DART 공시 (DART OpenAPI)
# ──────────────────────────────────────────

def fetch_dart_disclosure(tickers: list[Ticker], params: dict) -> dict:
    """
    DART 최근 공시 목록 수집.
    수집 기간: 오늘 기준 최근 lookback_days일 (기본 7일)

    Returns:
        {ticker: {"name": str, "corp_code": str, "period": str,
                  "disclosures": [{"rcept_no", "rcept_dt", "report_nm", "flr_nm", ...}]}}
    """
    import requests
    from src.settings import get_dart_api_key

    api_key = get_dart_api_key()
    corp_codes = _fetch_dart_corp_codes(api_key)

    lookback = params.get("lookback_days", 7)
    today = date.today()
    bgn_de = (today - timedelta(days=lookback)).strftime("%Y%m%d")
    end_de = today.strftime("%Y%m%d")

    results = {}
    for t in tickers:
        corp_code = corp_codes.get(t.ticker)
        if not corp_code:
            results[t.ticker] = {"name": t.name, "error": f"corp_code 미발견 ({t.ticker})"}
            continue
        try:
            resp = requests.get(
                "https://opendart.fss.or.kr/api/list.json",
                params={
                    "crtfc_key": api_key,
                    "corp_code": corp_code,
                    "bgn_de": bgn_de,
                    "end_de": end_de,
                    "page_count": 20,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            disclosures = data.get("list", []) if data.get("status") == "000" else []
            results[t.ticker] = {
                "name": t.name,
                "corp_code": corp_code,
                "period": f"{bgn_de}~{end_de}",
                "count": len(disclosures),
                "disclosures": disclosures,
            }
        except Exception as e:
            results[t.ticker] = {"name": t.name, "corp_code": corp_code, "error": str(e)}

        time.sleep(0.2)

    return results


# ──────────────────────────────────────────
# DART 재무제표 (DART OpenAPI)
# ──────────────────────────────────────────

def fetch_dart_financial(tickers: list[Ticker], params: dict) -> dict:
    """
    DART 단일회사 전체 재무제표 수집 (최근 사업연도 기준).

    Returns:
        {ticker: {"name": str, "corp_code": str, "bsns_year": str,
                  "fs_div": str, "financials": [{account_nm, thstrm_amount, ...}]}}
    """
    import requests
    from src.settings import get_dart_api_key

    api_key = get_dart_api_key()
    corp_codes = _fetch_dart_corp_codes(api_key)

    fs_div = params.get("fs_div", "CFS")           # CFS=연결, OFS=별도
    bsns_year = str(date.today().year - 1)          # 전년도 사업보고서
    reprt_code = "11011"                            # 11011=사업보고서

    results = {}
    for t in tickers:
        corp_code = corp_codes.get(t.ticker)
        if not corp_code:
            results[t.ticker] = {"name": t.name, "error": f"corp_code 미발견 ({t.ticker})"}
            continue
        try:
            resp = requests.get(
                "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
                params={
                    "crtfc_key": api_key,
                    "corp_code": corp_code,
                    "bsns_year": bsns_year,
                    "reprt_code": reprt_code,
                    "fs_div": fs_div,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            financials = data.get("list", []) if data.get("status") == "000" else []
            results[t.ticker] = {
                "name": t.name,
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
                "fs_div": fs_div,
                "count": len(financials),
                "financials": financials,
            }
        except Exception as e:
            results[t.ticker] = {"name": t.name, "corp_code": corp_code, "error": str(e)}

        time.sleep(0.3)

    return results


# ──────────────────────────────────────────
# PDF 파일 목록 스캔 (로컬 디렉터리)
# ──────────────────────────────────────────

def fetch_pdf_files(tickers: list[Ticker], params: dict) -> dict:
    """
    data_sources.json 의 params.directory 경로에서 PDF 파일 목록을 수집.
    본문 추출은 data_loading 단계에서 수행하며, 여기서는 경로·메타만 반환.

    Returns:
        {
            "directory": str,          # 스캔한 절대 경로
            "count": int,              # 발견된 PDF 수
            "files": [
                {"filename": str, "path": str, "size_kb": float},
                ...
            ]
        }
    """
    rel_dir: str = params.get("directory", "collected_datas/pdf_datas")
    pdf_dir = (_PROJECT_ROOT / rel_dir).resolve()

    if not pdf_dir.exists():
        return {
            "directory": str(pdf_dir),
            "count": 0,
            "files": [],
            "warning": f"디렉터리 없음: {pdf_dir}",
        }

    files = []
    for pdf_path in sorted(pdf_dir.glob("**/*.pdf")):
        files.append({
            "filename": pdf_path.name,
            "path": str(pdf_path),
            "size_kb": round(pdf_path.stat().st_size / 1024, 1),
        })

    return {
        "directory": str(pdf_dir),
        "count": len(files),
        "files": files,
    }
