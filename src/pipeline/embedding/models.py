"""
임베딩 결과를 담는 EmbeddedChunk 데이터 모델.
벡터DB 저장 단계(04)에서 이 모델을 소비한다.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmbeddedChunk:
    """
    단일 임베딩 결과 단위.

    Attributes:
        text:          원본 청크 텍스트
        source:        원본 출처 (URL / 파일 경로)
        source_type:   원본 소스 타입 (naver_news / dart_disclosure / pdf)
        chunk_index:   Document 내 청크 순번 (0-based)
        total_chunks:  Document의 전체 청크 수
        metadata:      청킹 메타 + 임베딩 메타
        embedding:     임베딩 벡터 (float 리스트)
        model:         임베딩에 사용한 모델명
    """
    text: str
    source: str
    source_type: str
    chunk_index: int
    total_chunks: int
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)
    model: str = ""

    def __repr__(self) -> str:
        preview = self.text[:60].replace("\n", " ")
        return (
            f"EmbeddedChunk({self.chunk_index+1}/{self.total_chunks} "
            f"source_type={self.source_type!r} dim={len(self.embedding)} "
            f"preview={preview!r})"
        )
