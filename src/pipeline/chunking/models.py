"""
청킹 결과를 담는 Chunk 데이터 모델.
임베딩 단계에서 Chunk.text 를 벡터화한다.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """
    단일 청크 단위.

    Attributes:
        text:          청크 텍스트
        source:        원본 Document.source (URL / 파일 경로)
        source_type:   원본 Document.source_type (naver_news / dart_disclosure / pdf)
        chunk_index:   이 Document 내 청크 순번 (0-based)
        total_chunks:  이 Document의 전체 청크 수
        metadata:      원본 메타 + 청킹 메타 (strategy, chunk_size 등)
    """
    text: str
    source: str
    source_type: str
    chunk_index: int
    total_chunks: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.text.strip()

    def __repr__(self) -> str:
        preview = self.text[:60].replace("\n", " ")
        return (
            f"Chunk({self.chunk_index+1}/{self.total_chunks} "
            f"source_type={self.source_type!r} preview={preview!r})"
        )
