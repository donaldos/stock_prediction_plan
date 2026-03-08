"""
DART 공시 문서 본문 수집.

dart_disclosure.json에 저장된 rcept_no 리스트를 입력받아
DART document.xml API로 실제 공시 HTML을 다운로드하고
텍스트를 추출해 Document 객체 리스트로 반환한다.

API:
  GET https://opendart.fss.or.kr/api/document.xml
      ?crtfc_key={key}&rcept_no={rcept_no}
  → ZIP 응답 → 내부 *.htm / *.html 파일 파싱
"""

from __future__ import annotations
import io
import re
import time
import zipfile
from typing import Any

from .models import Document

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    raise ImportError("pip install requests beautifulsoup4") from e


_DART_DOC_URL = "https://opendart.fss.or.kr/api/document.xml"


def _extract_text_from_zip(zip_bytes: bytes) -> str:
    """
    DART document.xml ZIP → HTML 파일 파싱 → 텍스트 추출.
    ZIP 안에 여러 파일이 있을 경우 *.htm / *.html 만 처리한다.
    """
    texts: list[str] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        html_files = [
            name for name in zf.namelist()
            if name.lower().endswith((".htm", ".html"))
        ]
        # 파일이 없으면 모든 파일 시도
        if not html_files:
            html_files = zf.namelist()

        for fname in html_files:
            with zf.open(fname) as f:
                raw = f.read()
            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)
            texts.append(text.strip())

    return "\n\n---\n\n".join(t for t in texts if t)


def load_disclosure(
    rcept_no: str,
    api_key: str,
    metadata: dict[str, Any] | None = None,
) -> Document | None:
    """
    단일 공시 문서 rcept_no → Document.

    Args:
        rcept_no: DART 접수번호 (예: "20240115000123")
        api_key: DART OpenAPI 키
        metadata: 추가 메타정보 (ticker, report_nm 등)

    Returns:
        Document 또는 None (실패 시)
    """
    meta = metadata or {}
    source_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"

    try:
        resp = requests.get(
            _DART_DOC_URL,
            params={"crtfc_key": api_key, "rcept_no": rcept_no},
            timeout=30,
        )
        resp.raise_for_status()
        text = _extract_text_from_zip(resp.content)
    except Exception as e:
        return None

    if not text.strip():
        return None

    return Document(
        text=text,
        source=source_url,
        source_type="dart_disclosure",
        metadata={**meta, "rcept_no": rcept_no},
    )


def load_disclosures(
    disclosures: list[dict[str, Any]],
    api_key: str,
    ticker: str = "",
    name: str = "",
    delay: float = 0.5,
) -> list[Document]:
    """
    dart_disclosure.json의 disclosures 리스트 → Document 리스트.

    Args:
        disclosures: [{"rcept_no": str, "report_nm": str, "rcept_dt": str, ...}, ...]
        api_key: DART OpenAPI 키
        ticker: 종목 코드 (metadata용)
        name: 종목명 (metadata용)
        delay: 요청 사이 대기 시간 (초)

    Returns:
        본문 추출 성공한 Document 리스트
    """
    documents: list[Document] = []

    for item in disclosures:
        rcept_no = item.get("rcept_no", "")
        if not rcept_no:
            continue

        doc = load_disclosure(
            rcept_no=rcept_no,
            api_key=api_key,
            metadata={
                "ticker": ticker,
                "name": name,
                "report_nm": item.get("report_nm", ""),
                "rcept_dt": item.get("rcept_dt", ""),
                "flr_nm": item.get("flr_nm", ""),
            },
        )
        if doc:
            documents.append(doc)
        time.sleep(delay)

    return documents


def load_from_collected(dart_disclosure_data: dict, api_key: str) -> list[Document]:
    """
    collected_datas/.../dart_disclosure.json 전체 dict를 받아
    모든 종목의 공시 본문 수집.

    Args:
        dart_disclosure_data: {ticker: {"name": str, "disclosures": [...], ...}, ...}
        api_key: DART OpenAPI 키

    Returns:
        전체 Document 리스트
    """
    all_docs: list[Document] = []
    for ticker, info in dart_disclosure_data.items():
        if "error" in info:
            continue
        docs = load_disclosures(
            disclosures=info.get("disclosures", []),
            api_key=api_key,
            ticker=ticker,
            name=info.get("name", ""),
        )
        all_docs.extend(docs)
    return all_docs
