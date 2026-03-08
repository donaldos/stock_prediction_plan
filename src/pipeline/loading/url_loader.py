"""
네이버 금융 뉴스 URL → 기사 본문 텍스트 수집.

naver_news.json에 저장된 article URL 리스트를 입력받아
각 기사의 본문을 크롤링하고 Document 객체 리스트로 반환한다.

URL 패턴:
  수집 시 저장된 URL: https://finance.naver.com/item/news_read.naver?...
  실제 본문 페이지:   https://n.news.naver.com/mnews/article/{oid}/{aid}
"""

from __future__ import annotations
import re
import time
from typing import Any
from urllib.parse import urlparse, parse_qs

from .models import Document

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    raise ImportError("pip install requests beautifulsoup4") from e


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _to_news_url(finance_url: str) -> str | None:
    """
    네이버 금융 URL → 네이버 뉴스 본문 URL 변환.

    예:
      https://finance.naver.com/item/news_read.naver?article_id=0005363788&office_id=215&...
      → https://n.news.naver.com/mnews/article/215/0005363788
    """
    parsed = urlparse(finance_url)
    qs = parse_qs(parsed.query)
    oid = qs.get("office_id", qs.get("oid", [None]))[0]
    aid = qs.get("article_id", qs.get("aid", [None]))[0]
    if oid and aid:
        return f"https://n.news.naver.com/mnews/article/{oid}/{aid}"
    return None


def _extract_body(html: bytes) -> str:
    """네이버 뉴스 본문 div#dic_area 에서 텍스트 추출."""
    soup = BeautifulSoup(html, "html.parser")
    body_div = soup.select_one("div#dic_area") or soup.select_one("div.newsct_article")
    if not body_div:
        return ""
    # 불필요한 태그 제거
    for tag in body_div(["script", "style", "figure", "figcaption"]):
        tag.decompose()
    text = body_div.get_text(separator="\n", strip=True)
    # 연속 공백/줄바꿈 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_articles(
    articles: list[dict[str, Any]],
    ticker: str = "",
    name: str = "",
    delay: float = 0.5,
) -> list[Document]:
    """
    naver_news.json의 articles 리스트 → Document 리스트.

    Args:
        articles: [{"title": str, "url": str, "date": str}, ...]
        ticker: 종목 코드 (metadata용)
        name: 종목명 (metadata용)
        delay: 요청 사이 대기 시간 (초)

    Returns:
        본문 추출 성공한 Document 리스트
    """
    documents: list[Document] = []

    for article in articles:
        url: str = article.get("url", "")
        title: str = article.get("title", "")
        date: str = article.get("date", "")

        news_url = _to_news_url(url)
        if not news_url:
            continue

        try:
            resp = requests.get(news_url, headers=_HEADERS, timeout=10)
            resp.raise_for_status()
            body = _extract_body(resp.content)
        except Exception:
            body = ""

        if not body:
            time.sleep(delay)
            continue

        documents.append(
            Document(
                text=body,
                source=news_url,
                source_type="naver_news",
                metadata={
                    "title": title,
                    "date": date,
                    "ticker": ticker,
                    "name": name,
                    "original_url": url,
                },
            )
        )
        time.sleep(delay)

    return documents


def load_from_collected(naver_news_data: dict) -> list[Document]:
    """
    collected_datas/.../naver_news.json 전체 dict를 받아 모든 종목의 기사 본문 수집.

    Args:
        naver_news_data: {ticker: {"name": str, "articles": [...]}, ...}

    Returns:
        전체 Document 리스트
    """
    all_docs: list[Document] = []
    for ticker, info in naver_news_data.items():
        if "error" in info:
            continue
        docs = load_articles(
            articles=info.get("articles", []),
            ticker=ticker,
            name=info.get("name", ""),
        )
        all_docs.extend(docs)
    return all_docs
