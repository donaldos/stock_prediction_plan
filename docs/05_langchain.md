# 05. RAG + LLM 예측

> **관련 Phase:** Phase 5 | **상태:** 구현 완료 (Claude 기본 / OpenAI / Gemini 선택)

---

## 개요

벡터DB에서 관련 청크를 검색(RAG)하고, 멀티종목 컨텍스트를 구성하여
LLM에 주가 방향 예측을 요청하는 파이프라인 단계.

- **기본 전략:** Claude (`claude-sonnet-4-6`)
- **선택 전략:** OpenAI (`gpt-4o`), Gemini (`gemini-2.0-flash`)
- 전략은 `config/pipeline.json`에서 선택하고, CLI `--llm-strategy`로 override 가능
- LangChain을 **사용하지 않음** — Anthropic/OpenAI/Google SDK 직접 호출

---

## 파일 구조

```
src/pipeline/rag/
├── __init__.py            # 공개 API: predict_and_save, load_prediction, PredictionOutput
├── base.py                # LLMStrategy ABC
├── models.py              # PredictionOutput 데이터 모델
├── context.py             # 컨텍스트 구성 + 시나리오 감지 (Case C / D)
├── prompt.py              # 프롬프트 빌더 (시나리오별 + Few-shot)
├── snapshot.py            # prediction_result.json 저장/로드/요약
├── predictor.py           # Predictor + predict_and_save (재시도 Case B)
└── strategies/
    ├── __init__.py
    ├── claude.py          # ClaudeStrategy (Anthropic SDK)
    ├── openai.py          # OpenAILLMStrategy (OpenAI SDK)
    └── gemini.py          # GeminiStrategy (Google Gemini SDK)
```

---

## 기술 스택

| 라이브러리 | 전략 | 설치 |
|------------|------|------|
| `anthropic` | `claude` (기본) | `pip install anthropic` |
| `openai` | `openai` | `pip install openai` (임베딩과 공유) |
| `google-genai` | `gemini` | `pip install google-genai` |

---

## 설계

### 전략 패턴 (Strategy Pattern)

```python
class LLMStrategy(ABC):
    @abstractmethod
    def predict(self, prompt_messages: list[dict]) -> PredictionOutput: ...

    @property @abstractmethod
    def name(self) -> str: ...

    @property @abstractmethod
    def model_name(self) -> str: ...

    @property @abstractmethod
    def params(self) -> dict: ...
```

| 전략 | 클래스 | 모델 | SDK |
|------|--------|------|-----|
| `claude` | `ClaudeStrategy` | `claude-sonnet-4-6` | `anthropic` |
| `openai` | `OpenAILLMStrategy` | `gpt-4o` | `openai` |
| `gemini` | `GeminiStrategy` | `gemini-2.0-flash` | `google-genai` |

---

### PredictionOutput 데이터 모델

```python
@dataclass
class PredictionOutput:
    ticker:           str       # 종목코드
    date:             str       # 예측 기준 날짜 (YYYY-MM-DD)
    prediction:       str       # '상승' | '하락' | '횡보'
    confidence_score: int       # LLM 자가 평가 1~10
    scenario_type:    str       # '일반' | '외부충격_상승' | '외부충격_하락'
    bull_case:        str       # 강세 근거
    bear_case:        str       # 약세 근거
    key_references:   list[str] # 참고 자료 목록
    evidence_count:   int       # 활용 근거 수
    low_confidence:   bool      # 3차 실패 후 강제 생성 여부
```

---

### 컨텍스트 구성 (`context.py`)

#### Case C: 시나리오 감지

SOX 지수 변동과 미국 5종목 평균 변동이 모두 ±3% 이상이면 외부충격 시나리오.

```python
def detect_scenario(collected_data: dict) -> str:
    # SOX 변동 + 미국 평균 변동 계산
    # 둘 다 ±3% 이상: 외부충격_상승 / 외부충격_하락
    # 미충족: 일반
```

#### Case D: 멀티종목 컨텍스트

| 블록 | 내용 |
|------|------|
| 메인 컨텍스트 | 예측 종목 주가 요약 + RAG 검색 결과 |
| 국내 컨텍스트 | 한미반도체, SK하이닉스 등 등락률·거래량 |
| 미국 컨텍스트 | NVDA, AMD, INTC, AVGO, QCOM 등락률 + SOX |

---

### 프롬프트 구성 (`prompt.py`)

시나리오별 시스템 프롬프트 분기:

| 시나리오 | 추가 지시 |
|----------|-----------|
| `일반` | 기본 분석 프롬프트 |
| `외부충격_상승` | 단기 모멘텀·외국인 수급 유입 강조 |
| `외부충격_하락` | 하방 리스크·외국인 수급 이탈 강조 |

LLM 출력 형식 (순수 JSON):
```json
{
  "ticker": "005930",
  "date": "2026-03-07",
  "prediction": "상승",
  "confidence_score": 8,
  "scenario_type": "일반",
  "bull_case": "HBM 수요 확대 공시로 중장기 실적 개선 기대",
  "bear_case": "글로벌 반도체 업황 불확실성",
  "key_references": ["삼성전자 4Q 실적 발표", "HBM 공급 확대 공시"],
  "evidence_count": 5
}
```

---

### 재시도 전략 — Case B: 신뢰도 검증 (`predictor.py`)

| 기준 | 임계값 |
|------|--------|
| `confidence_score` | ≥ 7 |
| `evidence_count` | ≥ 3 |

두 조건 모두 충족해야 통과. 실패 시 순차 재시도:

| 시도 | 전략 | 변경 사항 |
|------|------|-----------|
| 0차 (초기) | 기본 | top_k=5 |
| 1차 재시도 | Top-K 확장 | top_k → 10 |
| 2차 재시도 | Few-shot 추가 | 과거 유사 사례 프롬프트 주입 |
| 3차 (최종) | 강제 생성 | `low_confidence=True` 표기 |

---

### 스냅샷 (`snapshot.py`)

저장 파일: `{run_dir}/prediction_result.json`

```json
{
  "saved_at":     "2026-03-07T10:30:00",
  "llm_strategy": "claude",
  "model_name":   "claude-sonnet-4-6",
  "ticker":       "005930",
  "result": {
    "ticker":           "005930",
    "date":             "2026-03-07",
    "prediction":       "상승",
    "confidence_score": 8,
    "scenario_type":    "일반",
    ...
  }
}
```

| 함수 | 역할 |
|------|------|
| `save(output, path, meta)` | prediction_result.json 저장 |
| `load(path)` | PredictionOutput 로드 |
| `exists(path)` | 파일 존재 여부 |
| `summary(path)` | 로그용 한 줄 요약 |

---

## Config (`config/pipeline.json`)

```json
"llm": {
  "strategy": "claude",
  "ticker": "005930",
  "params": {
    "claude": {
      "model":       "claude-sonnet-4-6",
      "max_tokens":  1024,
      "temperature": 0.0
    },
    "openai": {
      "model":       "gpt-4o",
      "max_tokens":  1024,
      "temperature": 0.0
    },
    "gemini": {
      "model":       "gemini-2.0-flash",
      "max_tokens":  1024,
      "temperature": 0.0
    }
  }
}
```

RAG 검색 파라미터는 `vectordb.search`에서 가져온다:
```json
"vectordb": {
  "search": { "top_k": 5, "top_k_expanded": 10 }
}
```

---

## 실행 방법

```bash
# 기본 실행 (claude, config 기본값)
python3 -m src.main --predict

# LLM 전략 지정
python3 -m src.main --predict --llm-strategy claude
python3 -m src.main --predict --llm-strategy openai

# 강제 재예측
python3 -m src.main --predict --force-predict

# 전체 파이프라인 (수집 → ... → 벡터DB → 예측)
python3 -m src.main --all
```

### 스킵 조건

`{run_dir}/prediction_result.json`이 존재하면 자동 건너뜀.
`--force-predict` 플래그로 강제 재실행 가능.

---

## 공개 API (`src/pipeline/rag/__init__.py`)

```python
from src.pipeline.rag import predict_and_save, load_prediction, PredictionOutput

# 예측 실행 + 저장
output_path = predict_and_save(
    run_dir=run_dir,
    ticker="005930",
    strategy="claude",
    collection="stock_rag",
)

# 저장된 결과 로드
result = load_prediction(run_dir)
print(result.prediction, result.confidence_score)
```

---

## 환경 변수

선택한 전략에 해당하는 키만 설정하면 된다.

| 변수 | 전략 | 발급처 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | `claude` | https://console.anthropic.com |
| `OPENAI_API_KEY` | `openai` | https://platform.openai.com (임베딩과 공유) |
| `GOOGLE_API_KEY` | `gemini` | https://aistudio.google.com |

---

## 향후 과제

- [ ] `confidence_score ≥ 7` 및 `evidence_count ≥ 3` 임계값 파일럿 후 조정
- [ ] Few-shot 예시 데이터 실제 예측 사례로 교체
- [ ] SOX 임계값 ±3% 파일럿 운영 후 재검토
- [ ] 재시도 간 backoff 정책 (API rate limit 대비)
- [ ] ticker 다중 지원 (현재 단일 종목만 지원)
- [ ] filter_meta 활용 — 날짜 범위 필터로 RAG 정확도 향상
