# 06. LangGraph 오케스트레이션

> **관련 Phase:** Phase 6 | **상태:** 구현 완료

---

## 개요

Phase 5의 RAG + LLM 예측 로직을 LangGraph StateGraph 기반으로 재구성한 오케스트레이션 레이어.

- 명시적 **상태(State)** 관리로 노드 간 데이터 흐름 추적
- **Case B**: 신뢰도 검증 + 최대 3회 재시도 루프
- **Case C**: 미국 반도체 지수 기반 시나리오 자동 감지
- **Case D**: 국내 + 미국 참고 종목 멀티 컨텍스트 구성
- Phase 5 (`--predict`) 와 독립 실행 가능 (`--orchestrate`)

---

## 파일 구조

```
src/pipeline/orchestration/
├── __init__.py      # 공개 API: run_pipeline, run_and_save, load_result
├── state.py         # PipelineState TypedDict
├── nodes.py         # 모든 노드 함수
├── graph.py         # build_graph() → CompiledGraph
├── snapshot.py      # orchestration_result.json 저장/로드/요약
└── runner.py        # run_pipeline, run_and_save, load_result
```

---

## 기술 스택

| 라이브러리 | 용도 | 설치 |
|------------|------|------|
| `langgraph` | 상태 기반 워크플로우 | `pip install langgraph` |

> LLM 호출은 Phase 5의 전략 클래스(`ClaudeStrategy`, `OpenAILLMStrategy`, `GeminiStrategy`) 재사용

---

## 노드 흐름

```
[START]
   │
   ▼
[load_data]
   │  수집 데이터 JSON 로드 → collected_data
   ▼
[detect_scenario]               ← Case C
   │  SOX + 미국 5종목 평균 ±3% 감지
   │  → scenario_type: "일반" | "외부충격_상승" | "외부충격_하락"
   ▼
[build_context]                 ← Case D
   │  국내 참고 종목 컨텍스트 → domestic_context
   │  미국 참고 종목 컨텍스트 → us_context
   ▼
[request_llm]
   │  RAG 검색 (벡터DB top_k) → rag_chunks
   │  메인 컨텍스트 구성 → main_context
   │  프롬프트 빌드 (시나리오 + few_shot)
   │  LLM 호출 → llm_result
   ▼
[validate_resp] ──────────────  ← Case B (conditional edge)
   │
   ├── "pass"         ──────────▶ [generate_report] ──▶ [END]
   │     confidence ≥ 7
   │     evidence   ≥ 3
   │
   ├── "retry"        ──────────▶ [retry]
   │     retry_count < 3              │
   │                                  │ 재시도 파라미터 조정
   │                                  └──────▶ [request_llm]  (루프)
   │
   └── "force_report" ──────────▶ [force_report] ──▶ [END]
         retry_count ≥ 3              low_confidence=True
```

---

## 상태 (`state.py`)

```python
class PipelineState(TypedDict, total=False):
    # 입력
    run_dir, ticker, target_date, collection
    store_strategy, store_params
    llm_strategy, llm_params
    top_k, top_k_expanded

    # 노드 실행 중 채워지는 상태
    collected_data    # load_data 결과
    scenario_type     # detect_scenario 결과 (Case C)
    domestic_context  # build_context 결과 (Case D)
    us_context        # build_context 결과 (Case D)
    rag_chunks        # request_llm 중간 결과
    main_context      # request_llm 중간 결과
    llm_result        # PredictionOutput.to_dict()

    # 재시도 제어 (Case B)
    retry_count, use_few_shot, current_top_k

    # 최종
    report  # generate_report / force_report 결과
```

---

## 노드 상세 (`nodes.py`)

### `load_data`
Phase 5 `context.py`의 `load_collected_data()` 재사용.
`run_dir` 내 `*.json` 파일 (스냅샷 파일 제외)을 읽어 `collected_data`로 저장.

### `detect_scenario` — Case C

```python
# SOX + 미국 5종목 평균 변동이 모두 ±3% 이상이면 외부충격
if abs(sox_change) >= 3.0 and abs(us_avg) >= 3.0:
    scenario = "외부충격_상승" if sox_change > 0 else "외부충격_하락"
else:
    scenario = "일반"
```

### `build_context` — Case D

| 블록 | 대상 |
|------|------|
| `domestic_context` | 042700 (한미반도체), TBD, 000660 (SK하이닉스) |
| `us_context` | NVDA, AMD, INTC, AVGO, QCOM + SOX |

### `request_llm`
1. 벡터DB에서 `current_top_k`개 청크 RAG 검색
2. `build_main_context()` 호출
3. `build_messages()` 로 프롬프트 구성 (`use_few_shot` 반영)
4. `llm_strategy` 클래스로 LLM 호출
5. `llm_result` 저장

### `validate_resp` — Case B (conditional edge)

| 조건 | 임계값 | 실패 시 |
|------|--------|---------|
| `confidence_score` | ≥ 7 | 재시도 |
| `evidence_count` | ≥ 3 | 재시도 |

### `retry`

| retry_count | 적용 전략 |
|-------------|-----------|
| 0 → 1 | `current_top_k` → `top_k_expanded` (5 → 10) |
| 1 → 2 | `use_few_shot = True` |
| ≥ 3 | `force_report` 노드로 분기 (여기 도달 안 함) |

### `generate_report` / `force_report`
`llm_result`에 `low_confidence`, `retry_count`, `scenario_type`, `rag_chunk_count` 추가.

---

## Config (`config/pipeline.json`)

오케스트레이션은 `llm` + `vectordb` 섹션을 모두 참조한다:

```json
"llm": {
  "strategy": "claude",
  "ticker": "005930"
},
"vectordb": {
  "search": { "top_k": 5, "top_k_expanded": 10 }
}
```

---

## 실행 방법

```bash
# 기본 실행 (claude, config 기본값)
python3 -m src.main --orchestrate

# LLM 전략 지정
python3 -m src.main --orchestrate --llm-strategy claude
python3 -m src.main --orchestrate --llm-strategy openai

# 강제 재실행
python3 -m src.main --orchestrate --force-orchestrate
```

### 스킵 조건

`{run_dir}/orchestration_result.json`이 존재하면 자동 건너뜀.

### Phase 5 (`--predict`) vs Phase 6 (`--orchestrate`)

| 항목 | `--predict` | `--orchestrate` |
|------|-------------|-----------------|
| 구현 방식 | 절차형 (predictor.py) | LangGraph StateGraph |
| 상태 추적 | 없음 | PipelineState로 명시적 관리 |
| 저장 파일 | `prediction_result.json` | `orchestration_result.json` |
| 재시도 | 내부 루프 | 그래프 엣지 루프 |
| 시나리오 정보 | 결과에 포함 | 상태로 추적 가능 |

---

## 스냅샷 (`snapshot.py`)

저장 파일: `{run_dir}/orchestration_result.json`

```json
{
  "saved_at":     "2026-03-07T10:30:00",
  "ticker":       "005930",
  "target_date":  "2026-03-07",
  "llm_strategy": "claude",
  "scenario_type": "일반",
  "retry_count":  0,
  "report": {
    "prediction":       "상승",
    "confidence_score": 8,
    "low_confidence":   false,
    "rag_chunk_count":  5
  }
}
```

---

## 공개 API

```python
from src.pipeline.orchestration import run_and_save, run_pipeline, load_result

# 실행 + 저장
output_path = run_and_save(
    run_dir=run_dir,
    ticker="005930",
    llm_strategy="claude",
)

# 결과 로드
result = load_result(run_dir)
print(result["report"]["prediction"])
print(result["report"]["low_confidence"])
```

---

## 향후 과제

- [ ] `confidence_score ≥ 7` 임계값 파일럿 후 조정
- [ ] Few-shot 예시 실제 사례로 교체
- [ ] SOX 임계값 ±3% 파일럿 후 재검토
- [ ] LangGraph 그래프 시각화 (`graph.get_graph().draw_mermaid()`)
- [ ] 재시도 간 backoff 정책 (API rate limit 대비)
