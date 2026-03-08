"""
EmbeddingStrategy 추상 인터페이스.

모든 임베딩 전략은 이 클래스를 상속하고
embed(texts) 메서드 하나만 구현하면 된다.
"""

from __future__ import annotations
from abc import ABC, abstractmethod


class EmbeddingStrategy(ABC):
    """
    임베딩 전략 인터페이스.

    구현 클래스:
        BgeEmbedder     — BAAI/bge-m3 (로컬, sentence-transformers, 무료)
        UpstageEmbedder — Upstage Solar Embedding API
        OpenAIEmbedder  — OpenAI text-embedding-3-small API
    """

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        텍스트 리스트를 임베딩 벡터 리스트로 변환.

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            각 텍스트에 대응하는 float 벡터 리스트 (len(texts) == len(반환값))
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """전략 식별 이름 (metadata 기록용). 예: "bge", "upstage", "openai"."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """사용 모델 이름. 예: "BAAI/bge-m3", "solar-embedding-1-large"."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """임베딩 벡터 차원 수."""
        ...
