"""
LLM 전략 추상 기반 클래스.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pipeline.rag.models import PredictionOutput


class LLMStrategy(ABC):
    """RAG 예측 LLM 전략 인터페이스."""

    @abstractmethod
    def predict(self, prompt_messages: list[dict]) -> "PredictionOutput":
        """
        프롬프트 메시지를 받아 PredictionOutput 반환.

        Args:
            prompt_messages: [{"role": "system"|"user", "content": str}, ...]
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """전략 식별자 (예: 'claude', 'openai')."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """사용 모델 이름."""

    @property
    @abstractmethod
    def params(self) -> dict:
        """현재 전략 파라미터."""
