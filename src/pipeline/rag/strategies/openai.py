"""
OpenAI GPT LLM 전략.

기본 모델: gpt-4o
"""
from __future__ import annotations

import json
import logging

from src.pipeline.rag.base import LLMStrategy
from src.pipeline.rag.models import PredictionOutput

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o"
_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_TEMPERATURE = 0.0


class OpenAILLMStrategy(LLMStrategy):
    """OpenAI GPT를 사용하는 LLM 전략."""

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
    ):
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._client = None  # 지연 초기화

    @property
    def _openai(self):
        if self._client is None:
            from openai import OpenAI
            from src.settings import get_openai_api_key
            self._client = OpenAI(api_key=get_openai_api_key())
        return self._client

    def predict(self, prompt_messages: list[dict]) -> PredictionOutput:
        """OpenAI API 호출 → PredictionOutput 반환."""
        logger.debug("OpenAI 예측 요청 — model=%s", self._model)
        response = self._openai.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            response_format={"type": "json_object"},
            messages=prompt_messages,
        )

        raw_text = response.choices[0].message.content.strip()
        logger.debug("OpenAI 응답 raw: %s", raw_text[:200])
        return _parse_response(raw_text)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def params(self) -> dict:
        return {
            "model":       self._model,
            "max_tokens":  self._max_tokens,
            "temperature": self._temperature,
        }


def _parse_response(raw: str) -> PredictionOutput:
    """LLM 응답 JSON 파싱."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("LLM 응답 JSON 파싱 실패: %s\n원문: %s", exc, raw[:500])
        raise ValueError(f"LLM 응답이 유효한 JSON이 아닙니다: {exc}") from exc
    return PredictionOutput.from_dict(data)
