"""
Claude (Anthropic) LLM 전략.

기본 모델: claude-sonnet-4-6
"""
from __future__ import annotations

import json
import logging

from src.pipeline.rag.base import LLMStrategy
from src.pipeline.rag.models import PredictionOutput

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_TEMPERATURE = 0.0


class ClaudeStrategy(LLMStrategy):
    """Anthropic Claude를 사용하는 LLM 전략."""

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
    def _anthropic(self):
        if self._client is None:
            import anthropic
            from src.settings import get_anthropic_api_key
            self._client = anthropic.Anthropic(api_key=get_anthropic_api_key())
        return self._client

    def predict(self, prompt_messages: list[dict]) -> PredictionOutput:
        """Claude API 호출 → PredictionOutput 반환."""
        # Anthropic API는 system 메시지를 별도 파라미터로 받음
        system_content = ""
        user_messages = []
        for msg in prompt_messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                user_messages.append(msg)

        logger.debug("Claude 예측 요청 — model=%s", self._model)
        response = self._anthropic.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system_content,
            messages=user_messages,
        )

        raw_text = response.content[0].text.strip()
        logger.debug("Claude 응답 raw: %s", raw_text[:200])
        return _parse_response(raw_text)

    @property
    def name(self) -> str:
        return "claude"

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
    """LLM 응답 문자열에서 JSON을 추출해 PredictionOutput으로 변환."""
    # 코드 블록 제거 (```json ... ```)
    if "```" in raw:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        raw = raw[start:end] if start != -1 else raw

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("LLM 응답 JSON 파싱 실패: %s\n원문: %s", exc, raw[:500])
        raise ValueError(f"LLM 응답이 유효한 JSON이 아닙니다: {exc}") from exc

    return PredictionOutput.from_dict(data)
