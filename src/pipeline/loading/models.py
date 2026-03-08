"""
로딩(크롤링) 결과를 담는 공통 데이터 모델.
청킹 단계에서 이 Document 객체를 입력으로 받는다.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """
    단일 문서 단위.

    Attributes:
        text: 추출된 본문 텍스트
        source: 원본 URL 또는 파일 경로
        source_type: 'naver_news' | 'dart_disclosure' | 'pdf'
        metadata: 제목, 날짜, ticker 등 부가 정보
    """
    text: str
    source: str
    source_type: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.text.strip()

    def __repr__(self) -> str:
        preview = self.text[:80].replace("\n", " ")
        return (
            f"Document(source_type={self.source_type!r}, "
            f"source={self.source!r}, preview={preview!r})"
        )
