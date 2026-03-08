"""
토큰 단위 청킹 전략 (tiktoken).

LLM 컨텍스트 윈도우 초과 방지에 정확하다.
cl100k_base 인코딩은 GPT-4 / Claude 와 호환된다.

의존성: tiktoken   pip install tiktoken
"""

from __future__ import annotations
from ..base import ChunkStrategy


class TokenChunker(ChunkStrategy):
    """
    tiktoken 으로 토큰 수를 기준으로 분할.

    Args:
        chunk_tokens: 청크당 최대 토큰 수 (기본 256)
        overlap:      오버랩 토큰 수 (기본 32)
        encoding:     tiktoken 인코딩 이름 (기본 cl100k_base)
    """

    def __init__(
        self,
        chunk_tokens: int = 256,
        overlap: int = 32,
        encoding: str = "cl100k_base",
    ):
        try:
            import tiktoken
        except ImportError as e:
            raise ImportError("pip install tiktoken") from e

        if overlap >= chunk_tokens:
            raise ValueError("overlap 은 chunk_tokens 보다 작아야 합니다.")

        self._enc = tiktoken.get_encoding(encoding)
        self._chunk_tokens = chunk_tokens
        self._overlap = overlap
        self._encoding = encoding

    @property
    def name(self) -> str:
        return "token"

    @property
    def params(self) -> dict:
        return {
            "chunk_tokens": self._chunk_tokens,
            "overlap": self._overlap,
            "encoding": self._encoding,
        }

    def split(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []

        token_ids = self._enc.encode(text)
        step = self._chunk_tokens - self._overlap
        chunks: list[str] = []
        start = 0
        while start < len(token_ids):
            chunk_ids = token_ids[start: start + self._chunk_tokens]
            chunk_text = self._enc.decode(chunk_ids).strip()
            if chunk_text:
                chunks.append(chunk_text)
            start += step

        return chunks
