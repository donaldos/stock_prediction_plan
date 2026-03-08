# 07. 리포트 & 슬랙 발송

> **관련 Phase:** Phase 7 | **상태:** 구현 완료

---

## 개요

LangGraph에서 생성된 `orchestration_result.json`을 Slack Block Kit 메시지로 포맷팅하여
Incoming Webhook으로 발송하는 모듈.

- **외부 라이브러리 불필요** — Python 표준 라이브러리 `urllib`만 사용
- Block Kit 기반 리치 UI (사이드바 색상, 섹션 구분, 컨텍스트 풋터)
- `low_confidence=True`인 경우 경고 배너 자동 추가

---

## 파일 구조

```
src/pipeline/notification/
├── __init__.py   # 공개 API: send_report, format_report
└── slack.py      # Block Kit 포맷터 + Webhook 발송
```

---

## 기술 스택

| 구성 요소 | 구현 방법 |
|-----------|-----------|
| 메시지 포맷 | Slack Block Kit (`attachments` + `blocks`) |
| HTTP 전송 | Python `urllib.request` (표준 라이브러리, 추가 설치 불필요) |
| Webhook 인증 | Incoming Webhook URL (`.env`의 `SLACK_WEBHOOK_URL`) |

---

## 설계 상세

### 발송 시나리오

| 상황 | 메시지 유형 | 사이드바 색상 |
|------|-------------|---------------|
| `confidence_score` ≥ 8 | 정상 리포트 | 초록 (`#2ecc71`) |
| `confidence_score` 6~7 | 정상 리포트 | 노랑 (`#f1c40f`) |
| `confidence_score` < 6 | 정상 리포트 | 빨강 (`#e74c3c`) |
| `low_confidence=True` | ⚠️ 경고 배너 + 리포트 | 빨강 |

### Slack Block Kit 메시지 구조

```
┌─────────────────────────────────────────────────┐
│ ⚠️ 신뢰도 낮음 경고 배너 (low_confidence=True 시만)│
├─────────────────────────────────────────────────┤
│ 📊 [005930] 주가 예측 리포트 · 2026-03-08  ← 헤더  │
├─────────────────────────────────────────────────┤
│ 예측: 📈 상승  |  신뢰도: ●●●●●●●○○○ 7/10       │  ← 4-column fields
│ 시나리오: 일반  |  근거 수: 4건                   │
├─────────────────────────────────────────────────┤
│ 🟢 강세 근거                                      │
│ 2026년 영업이익 전망 상향 조정...                  │
├─────────────────────────────────────────────────┤
│ 🔴 약세 리스크                                    │
│ 단기 변동성 가능성...                              │
├─────────────────────────────────────────────────┤
│ 📎 참고 자료 (2건)                                │
│ • Daishin Securities 보고서: ...                 │
│ • 장내매수 및 매도 데이터                          │
├─────────────────────────────────────────────────┤
│ 종목코드: `005930` | 예측일: 2026-03-08 | 재시도: 2회│ ← 컨텍스트 풋터
└─────────────────────────────────────────────────┘
```

---

## 공개 API (`slack.py`)

### `format_report(report) → dict`

`report` 딕셔너리를 Slack API payload로 변환. 전송 없이 payload만 반환.

```python
from src.pipeline.notification.slack import format_report

report = {
    "ticker": "005930",
    "date": "2026-03-08",
    "prediction": "상승",
    "confidence_score": 7,
    "scenario_type": "일반",
    "bull_case": "2026년 영업이익 전망 상향 조정",
    "bear_case": "단기 변동성 가능성",
    "key_references": ["Daishin Securities 보고서", "장내 매수 데이터"],
    "evidence_count": 4,
    "low_confidence": False,
    "retry_count": 2,
}

payload = format_report(report)  # Slack API JSON dict
```

### `send_report(report, webhook_url)`

포맷팅 + Webhook POST 전송.

```python
from src.pipeline.notification.slack import send_report

send_report(report, webhook_url="https://hooks.slack.com/services/...")
```

### `send_from_result_file(result_path, webhook_url)`

`orchestration_result.json` 경로를 받아 직접 전송.

```python
from src.pipeline.notification.slack import send_from_result_file
from pathlib import Path

send_from_result_file(
    Path("collected_datas/2026_0308_10/orchestration_result.json"),
    webhook_url="https://hooks.slack.com/services/...",
)
```

---

## Slack Webhook URL 발급

1. [https://api.slack.com/apps](https://api.slack.com/apps) → **"Create New App"** → "From scratch"
2. 좌측 **"Incoming Webhooks"** → 토글 **On**
3. **"Add New Webhook to Workspace"** → 채널 선택
4. 생성된 URL 복사 → `.env`에 저장

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../XXXX...
```

> 채널마다 URL이 다르므로, 채널을 변경할 경우 URL도 교체해야 한다.

---

## 환경 변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `SLACK_WEBHOOK_URL` | ✅ | Slack Incoming Webhook URL |

---

## 실행 방법

```bash
# orchestration_result.json → Slack 발송
python3 -m src.main --notify

# 오케스트레이션 실행 후 바로 발송
python3 -m src.main --orchestrate --notify

# 전체 파이프라인 (수집 → ... → 오케스트레이션 → Slack 발송)
python3 -m src.main --all
```

### 스킵 조건

없음 — `--notify`는 항상 최신 `orchestration_result.json`을 읽어 발송한다.

---

## 스냅샷 입력 형식

`orchestration_result.json`의 `"report"` 키를 읽는다:

```json
{
  "saved_at": "2026-03-08T10:07:32",
  "ticker": "005930",
  "llm_strategy": "openai",
  "report": {
    "ticker":           "005930",
    "date":             "2026-03-08",
    "prediction":       "상승",
    "confidence_score": 7,
    "scenario_type":    "일반",
    "bull_case":        "...",
    "bear_case":        "...",
    "key_references":   ["...", "..."],
    "evidence_count":   4,
    "low_confidence":   false,
    "retry_count":      2,
    "rag_chunk_count":  10
  }
}
```

---

## 향후 과제

- [ ] 오후 발송 시 당일 예측 정확도 피드백 메시지 포맷 설계
- [ ] 발송 실패 시 재시도 정책 (현재: 단순 예외 raise)
- [ ] 종목별 채널 분리 지원 (`SLACK_WEBHOOK_URL_005930` 등)
- [ ] 에러 발생 시 별도 채널로 오류 알림 전송
