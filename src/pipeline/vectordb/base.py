"""
VectorDBStrategy 추상 인터페이스.

모든 벡터DB 전략은 이 클래스를 상속하고
upsert / search 두 메서드를 구현하면 된다.
"""

from __future__ import annotations
from abc import ABC, abstractmethod

from .models import SearchResult


class VectorDBStrategy(ABC):
    """
    벡터DB 전략 인터페이스.

    구현 클래스:
        ChromaStrategy   — 로컬 파일 기반 벡터DB (파일럿, 기본)
        PineconeStrategy — 관리형 클라우드 벡터DB (운영)
    """

    @abstractmethod
    def upsert(
        self,
        embedded_chunks: list,
        collection: str,
    ) -> int:
        """
        EmbeddedChunk 리스트를 벡터DB에 upsert.

        Args:
            embedded_chunks: list[EmbeddedChunk]
            collection:      컬렉션(또는 네임스페이스) 이름

        Returns:
            upsert 된 건수
        """
        ...

    @abstractmethod
    def search(
        self,
        query_vector: list[float],
        collection: str,
        top_k: int = 5,
        filter_meta: dict | None = None,
    ) -> list[SearchResult]:
        """
        쿼리 벡터와 유사한 문서 검색.

        Args:
            query_vector: 검색 쿼리 임베딩 벡터
            collection:   검색 대상 컬렉션 이름
            top_k:        반환할 최대 결과 수
            filter_meta:  메타데이터 필터 조건 (선택)

        Returns:
            SearchResult 리스트 (유사도 내림차순)
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """전략 식별 이름. 예: "chroma", "pinecone"."""
        ...

    @property
    @abstractmethod
    def params(self) -> dict:
        """전략 파라미터 (metadata 기록용)."""
        ...
