"""
Google Gemini LLM 전략.

기본 모델: gemini-2.0-flash
SDK: google-genai (pip install google-genai)

Gemini API는 system_instruction을 contents와 분리하여 전달한다.
JSON 응답은 response_mime_type="application/json"으로 강제한다.
"""
from __future__ import annotations

import json
import logging

from src.pipeline.rag.base import LLMStrategy
from src.pipeline.rag.models import PredictionOutput

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.0-flash"
_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_TEMPERATURE = 0.0


class GeminiStrategy(LLMStrategy):
    """Google Gemini를 사용하는 LLM 전략."""

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
    def _genai(self):
        if self._client is None:
            from google import genai
            from src.settings import get_google_api_key
            self._client = genai.Client(api_key=get_google_api_key())
        return self._client

    def predict(self, prompt_messages: list[dict]) -> PredictionOutput:
        """Gemini API 호출 → PredictionOutput 반환."""
        from google.genai import types

        # system / user 메시지 분리
        system_content = ""
        user_parts: list[str] = []
        for msg in prompt_messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                user_parts.append(msg["content"])

        user_content = "\n\n".join(user_parts)

        logger.debug("Gemini 예측 요청 — model=%s", self._model)
        response = self._genai.models.generate_content(
            model=self._model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_content,
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
                response_mime_type="application/json",
            ),
        )

        raw_text = response.text.strip()
        logger.debug("Gemini 응답 raw: %s", raw_text[:200])
        return _parse_response(raw_text)

    @property
    def name(self) -> str:
        return "gemini"

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
    # Gemini는 response_mime_type=json 설정 시 순수 JSON 반환
    # 혹시 마크다운 감싸기가 있을 경우 대비
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
