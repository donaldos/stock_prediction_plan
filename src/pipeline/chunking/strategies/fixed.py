"""
고정 크기 청킹 전략.
외부 의존성 없음 — 순수 Python.
"""

from __future__ import annotations
from ..base import ChunkStrategy


class FixedSizeChunker(ChunkStrategy):
    """
    문자 수 기준 고정 크기로 분할. 오버랩 지원.

    Args:
        chunk_size: 청크당 최대 문자 수 (기본 500)
        overlap:    인접 청크 간 겹치는 문자 수 (기본 50)
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        if overlap >= chunk_size:
            raise ValueError("overlap 은 chunk_size 보다 작아야 합니다.")
        self._chunk_size = chunk_size
        self._overlap = overlap

    @property
    def name(self) -> str:
        return "fixed"

    @property
    def params(self) -> dict:
        return {"chunk_size": self._chunk_size, "overlap": self._overlap}

    def split(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []

        step = self._chunk_size - self._overlap
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + self._chunk_size
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += step

        return chunks
