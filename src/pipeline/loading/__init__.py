"""
src/loading — 크롤링/로딩 모듈.

청킹 이전 단계로, 수집된 URL·공시번호·PDF 파일에서
텍스트 본문을 추출해 Document 객체를 생성한다.

주요 모듈:
    models        — Document 공통 데이터 모델
    url_loader    — 네이버 뉴스 기사 본문 수집
    dart_doc_loader — DART 공시 문서 본문 수집
    pdf_loader    — PDF 파일 텍스트 추출
"""

from .models import Document
from .url_loader import load_articles, load_from_collected as load_news
from .dart_doc_loader import load_disclosures, load_from_collected as load_dart
from .pdf_loader import load_pdf, load_pdfs_from_dir, load_from_collected as load_pdf_collected
from .loader import load_and_save, load_snapshot
from . import snapshot

__all__ = [
    "Document",
    "load_articles",
    "load_news",
    "load_disclosures",
    "load_dart",
    "load_pdf",
    "load_pdfs_from_dir",
    "load_pdf_collected",
    "load_and_save",
    "load_snapshot",
    "snapshot",
]
