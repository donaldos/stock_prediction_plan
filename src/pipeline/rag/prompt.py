"""
LLM 예측 요청 프롬프트 빌더.

세 가지 시나리오(일반 / 외부충격_상승 / 외부충격_하락)에 따라
시스템 프롬프트와 사용자 프롬프트를 구성한다.
"""
from __future__ import annotations

from src.pipeline.rag.context import SCENARIO_SHOCK_DOWN, SCENARIO_SHOCK_UP

_SYSTEM_BASE = """\
당신은 한국 주식 시장 분석 전문가입니다.
주어진 데이터를 바탕으로 종목의 당일 주가 방향을 예측하고,
반드시 아래 JSON 형식으로만 응답하십시오.
다른 텍스트, 마크다운 코드 블록 없이 순수 JSON만 출력하십시오.

출력 형식:
{
  "ticker": "<종목코드>",
  "date": "<YYYY-MM-DD>",
  "prediction": "상승 | 하락 | 횡보",
  "confidence_score": <1~10 정수>,
  "scenario_type": "<시나리오>",
  "bull_case": "<강세 근거>",
  "bear_case": "<약세 근거>",
  "key_references": ["<참고자료1>", "<참고자료2>"],
  "evidence_count": <참고된 근거 수 정수>
}

규칙:
- confidence_score: 데이터 충분도와 예측 확신도를 1(매우 낮음)~10(매우 높음)으로 자가 평가
- evidence_count: 실제 활용한 뉴스·공시·주가 데이터 항목 수
- key_references: 판단에 직접 기여한 자료 최대 5개
"""

_SYSTEM_SHOCK_UP = """\
현재 미국 반도체 시장에 급등 충격이 발생했습니다.
SOX 지수와 미국 주요 반도체 종목이 동반 급등하고 있으므로,
단기 모멘텀과 외국인 수급 유입 가능성을 특별히 강조하여 분석하십시오.
"""

_SYSTEM_SHOCK_DOWN = """\
현재 미국 반도체 시장에 급락 충격이 발생했습니다.
SOX 지수와 미국 주요 반도체 종목이 동반 급락하고 있으므로,
하방 리스크와 외국인 수급 이탈 가능성을 특별히 강조하여 분석하십시오.
"""

_USER_TEMPLATE = """\
{main_context}

{domestic_context}

{us_context}

## 시나리오 타입: {scenario_type}

## 예측 날짜: {date}

위 데이터를 바탕으로 {ticker}의 {date} 당일 주가 방향을 예측하십시오.
"""

_FEW_SHOT_EXAMPLE = """
## Few-shot 참고 예시 (이전 예측 사례)

예시 1 — 외부충격_상승 시나리오:
입력: SOX +4.2%, NVDA +5.1%, SK하이닉스 +2.3%
출력:
{
  "prediction": "상승",
  "confidence_score": 8,
  "bull_case": "미국 반도체 동반 급등으로 국내 수혜 기대, SK하이닉스 선행 상승",
  "bear_case": "단기 과열 우려, 원/달러 환율 강세",
  "evidence_count": 6
}

예시 2 — 일반 시나리오:
입력: SOX -0.5%, 삼성전자 HBM 공급 확대 공시
출력:
{
  "prediction": "상승",
  "confidence_score": 7,
  "bull_case": "HBM 수요 확대 공시로 중장기 실적 개선 기대",
  "bear_case": "글로벌 반도체 업황 불확실성 지속",
  "evidence_count": 4
}
"""


def build_messages(
    ticker: str,
    date: str,
    main_context: str,
    domestic_context: str,
    us_context: str,
    scenario_type: str,
    use_few_shot: bool = False,
) -> list[dict]:
    """
    LLM API 요청용 메시지 리스트 구성.

    Args:
        ticker:           예측 대상 종목코드
        date:             예측 기준 날짜
        main_context:     메인 종목 컨텍스트 블록
        domestic_context: 국내 참고 종목 컨텍스트
        us_context:       미국 참고 종목 컨텍스트
        scenario_type:    시나리오 타입
        use_few_shot:     True이면 Few-shot 예시를 시스템 프롬프트에 추가

    Returns:
        [{"role": "system", "content": ...}, {"role": "user", "content": ...}]
    """
    # 시나리오별 추가 지시 결합
    system_extra = ""
    if scenario_type == SCENARIO_SHOCK_UP:
        system_extra = _SYSTEM_SHOCK_UP
    elif scenario_type == SCENARIO_SHOCK_DOWN:
        system_extra = _SYSTEM_SHOCK_DOWN

    few_shot = _FEW_SHOT_EXAMPLE if use_few_shot else ""
    system_content = _SYSTEM_BASE + system_extra + few_shot

    user_content = _USER_TEMPLATE.format(
        main_context=main_context,
        domestic_context=domestic_context,
        us_context=us_context,
        scenario_type=scenario_type,
        date=date,
        ticker=ticker,
    )

    return [
        {"role": "system", "content": system_content.strip()},
        {"role": "user",   "content": user_content.strip()},
    ]
