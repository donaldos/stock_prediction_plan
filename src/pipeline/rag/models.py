"""
RAG 파이프라인 데이터 모델.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PredictionOutput:
    """
    LLM 예측 결과 구조.

    Attributes:
        ticker:           종목코드
        date:             예측 기준 날짜 (YYYY-MM-DD)
        prediction:       예측 방향 ('상승' | '하락' | '횡보')
        confidence_score: LLM 자가 평가 신뢰도 (1~10)
        scenario_type:    시나리오 타입 ('일반' | '외부충격_상승' | '외부충격_하락')
        bull_case:        강세 근거 텍스트
        bear_case:        약세 근거 텍스트
        key_references:   참고 자료 목록
        evidence_count:   활용된 근거 수
        low_confidence:   신뢰도 낮음 경고 여부 (3차 실패 후 강제 생성 시 True)
    """
    ticker:           str
    date:             str
    prediction:       str
    confidence_score: int
    scenario_type:    str
    bull_case:        str
    bear_case:        str
    key_references:   list[str] = field(default_factory=list)
    evidence_count:   int = 0
    low_confidence:   bool = False

    def to_dict(self) -> dict:
        return {
            "ticker":           self.ticker,
            "date":             self.date,
            "prediction":       self.prediction,
            "confidence_score": self.confidence_score,
            "scenario_type":    self.scenario_type,
            "bull_case":        self.bull_case,
            "bear_case":        self.bear_case,
            "key_references":   self.key_references,
            "evidence_count":   self.evidence_count,
            "low_confidence":   self.low_confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PredictionOutput":
        return cls(
            ticker=d.get("ticker", ""),
            date=d.get("date", ""),
            prediction=d.get("prediction", ""),
            confidence_score=int(d.get("confidence_score", 0)),
            scenario_type=d.get("scenario_type", "일반"),
            bull_case=d.get("bull_case", ""),
            bear_case=d.get("bear_case", ""),
            key_references=d.get("key_references", []),
            evidence_count=int(d.get("evidence_count", 0)),
            low_confidence=bool(d.get("low_confidence", False)),
        )
