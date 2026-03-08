"""
ChunkStrategy 추상 인터페이스.

모든 청킹 전략은 이 클래스를 상속하고
split(text) 메서드 하나만 구현하면 된다.
"""

from __future__ import annotations
from abc import ABC, abstractmethod


class ChunkStrategy(ABC):
    """
    청킹 전략 인터페이스.

    구현 클래스:
        FixedSizeChunker   — 고정 크기 + 오버랩
        RecursiveChunker   — 구분자 재귀 분할 (LangChain)
        SentenceChunker    — 문장 단위 (kss)
        TokenChunker       — 토큰 단위 (tiktoken)
    """

    @abstractmethod
    def split(self, text: str) -> list[str]:
        """
        텍스트를 청크 문자열 리스트로 분할.

        Args:
            text: 원본 텍스트

        Returns:
            비어있지 않은 청크 문자열 리스트
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """전략 식별 이름 (metadata 기록용)."""
        ...

    @property
    @abstractmethod
    def params(self) -> dict:
        """전략 파라미터 (metadata 기록용)."""
        ...
