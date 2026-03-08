"""
벡터DB 검색 결과를 담는 SearchResult 데이터 모델.
LangChain/LangGraph RAG 단계(05)에서 이 모델을 소비한다.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """
    단일 유사 문서 검색 결과.

    Attributes:
        text:        청크 텍스트
        source:      원본 출처 (URL / 파일 경로)
        source_type: 소스 타입 (naver_news / dart_disclosure / pdf)
        score:       유사도 점수 (높을수록 유사, 범위는 DB마다 다름)
        metadata:    원본 메타데이터 (날짜, 제목, 전략 정보 등)
    """
    text: str
    source: str
    source_type: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        preview = self.text[:60].replace("\n", " ")
        return (
            f"SearchResult(score={self.score:.4f} "
            f"source_type={self.source_type!r} preview={preview!r})"
        )
