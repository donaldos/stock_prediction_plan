"""
재귀 문자 분할 전략 (LangChain RecursiveCharacterTextSplitter).

한국어 구분자(\n\n → \n → . → 。→ " " → "")를 순서대로 시도해
청크 크기 이하로 분할한다.

의존성: langchain-text-splitters
"""

from __future__ import annotations
from ..base import ChunkStrategy


# 한국어 + 영문 혼용 구분자 순서
_KO_SEPARATORS = ["\n\n", "\n", ".", "。", "!", "？", "?", " ", ""]


class RecursiveChunker(ChunkStrategy):
    """
    LangChain RecursiveCharacterTextSplitter 래퍼.
    한국어·영문 혼용 문서에 가장 무난한 기본 전략.

    Args:
        chunk_size: 청크당 최대 문자 수 (기본 500)
        overlap:    인접 청크 간 겹치는 문자 수 (기본 50)
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except ImportError as e:
            raise ImportError("pip install langchain-text-splitters") from e

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=_KO_SEPARATORS,
        )
        self._chunk_size = chunk_size
        self._overlap = overlap

    @property
    def name(self) -> str:
        return "recursive"

    @property
    def params(self) -> dict:
        return {"chunk_size": self._chunk_size, "overlap": self._overlap}

    def split(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        return [c for c in self._splitter.split_text(text) if c.strip()]
