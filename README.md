# 주가 지표 예측 리포트 자동화 시스템

> **버전:** v1.5 | **최종 수정:** 2026-05-12 | **상태:** 운영 중

---

## 프로젝트 개요

특정 시간에 스케줄러가 자동 실행되어, 지정 종목의 당일 주가 지표를 예측하는 리포트를 생성하고 Slack으로 발송하는 AI 기반 자동화 파이프라인.

각 파이프라인 단계는 **전략 패턴(Strategy Pattern)**으로 구현되어 있어, 청킹·임베딩·벡터DB·LLM 등을 `config/pipeline.json` 또는 CLI 인자로 자유롭게 교체할 수 있다.

---

## 전체 아키텍처

```
[스케줄러: GitHub Actions cron — 평일 18:00 KST]
    │
    ▼
[01. 데이터 수집] ── KRX 주가, 투자자별 매매, 뉴스/공시, 재무제표, 미국 반도체 주가/SOX
    │                 (ThreadPoolExecutor 병렬 수집 + 재시도 정책)
    ▼
[02. 텍스트 로딩] ── PDF/JSON 텍스트 추출 (pdfplumber / pymupdf / pdfminer / PyPDF2)
    │
    ▼
[03. 청킹] ──────── 텍스트 분할 (recursive / sentence / token / fixed)
    │
    ▼
[04. 임베딩] ────── 텍스트 → 벡터 변환 (BGE-M3 / Upstage Solar / OpenAI)
    │
    ▼
[05. 벡터 DB] ───── 벡터 저장 및 유사도 검색 (Chroma / Pinecone)
    │
    ▼
[06. RAG + LLM] ── 관련 청크 검색 → 예측 요청 (Claude / GPT-4o / Gemini 2.0 Flash)
    │
    ▼
[07. LangGraph] ── 시나리오 분기 / 신뢰도 검증 / 재시도 (최대 3회)
    │
    ▼
[08. Slack 발송] ── Block Kit 리포트 → Incoming Webhook 전송
```

---

## LangGraph 오케스트레이션 흐름

> 구현 파일: `src/pipeline/orchestration/` | 상세 설계: `docs/06_langgraph.md`

Phase 5의 RAG + LLM 예측 로직을 LangGraph `StateGraph` 기반으로 재구성한 오케스트레이션 레이어.
`PipelineState` TypedDict로 노드 간 데이터 흐름을 명시적으로 추적하며, 3가지 시나리오 분기(Case B/C/D)를 그래프 엣지로 표현한다.

### 노드 흐름도

```
[START]
   │
   ▼
[load_data]                     수집 데이터 JSON 로드 → collected_data
   │
   ▼
[detect_scenario]               ← Case C: 외부충격 시나리오 감지
   │                              SOX + 미국 5종목 평균 ±3% 판단
   │                              → scenario_type: "일반" | "외부충격_상승" | "외부충격_하락"
   ▼
[build_context]                 ← Case D: 멀티종목 컨텍스트 구성
   │                              → domestic_context (한미반도체, SK하이닉스 등)
   │                              → us_context (NVDA, AMD, INTC, AVGO, QCOM + SOX)
   ▼
[request_llm]                   RAG 검색(벡터DB top_k) + 프롬프트 빌드 + LLM 호출
   │                              → rag_chunks, main_context, llm_result
   ▼
[validate_resp] ──────────────  ← Case B: 신뢰도 검증 (conditional edge)
   │
   ├── "pass"                   confidence ≥ 7 AND evidence ≥ 3
   │     └──▶ [generate_report] ──▶ [END]
   │
   ├── "retry"                  검증 실패 AND retry_count < 3
   │     └──▶ [retry] ──▶ [request_llm]  (루프 재진입)
   │
   └── "force_report"           검증 실패 AND retry_count ≥ 3
         └──▶ [force_report] ──▶ [END]    (low_confidence=True 표기)
```

### Case B — 신뢰도 검증 + 자동 재시도

LLM 응답의 품질을 `validate_resp` 노드에서 자동 검증한다. 두 조건을 **모두** 충족해야 통과한다.

| 검증 항목 | 임계값 | 설명 |
|-----------|--------|------|
| `confidence_score` | ≥ 7 | LLM이 자가 평가한 예측 확신도 (1~10) |
| `evidence_count` | ≥ 3 | LLM이 실제 활용한 근거 데이터 수 |

검증 실패 시 `retry` 노드에서 파라미터를 조정한 뒤 `request_llm`으로 재진입한다.

| 재시도 횟수 | 조정 전략 | 상태 변경 |
|-------------|-----------|-----------|
| 1차 | RAG 검색 범위 확장 | `current_top_k`: 5 → 10 (`top_k_expanded`) |
| 2차 | Few-shot 예시 추가 | `use_few_shot`: True (프롬프트에 예측 사례 2건 포함) |
| 3차 실패 | 강제 리포트 생성 | `force_report` 노드 → `low_confidence=True` 표기 |

강제 생성된 리포트는 Slack 발송 시 상단에 `⚠️ 신뢰도 낮음` 경고 배너가 포함된다.

### Case C — 외부충격 시나리오 감지

`detect_scenario` 노드에서 미국 반도체 시장의 급변을 감지하여 LLM 프롬프트에 시나리오별 추가 지시를 주입한다.

**발동 조건** — 아래 두 조건을 **모두** 충족해야 한다:

| 조건 | 대상 | 임계값 |
|------|------|--------|
| SOX 지수 등락률 | ^SOX 전일 대비 | ±3% 이상 |
| 미국 5종목 평균 등락률 | NVDA, AMD, INTC, AVGO, QCOM | ±3% 이상 |

**시나리오 분류:**

| 시나리오 타입 | 조건 | 프롬프트 추가 지시 |
|---------------|------|-------------------|
| `일반` | 임계값 미달 | 기본 시스템 프롬프트만 사용 |
| `외부충격_상승` | SOX > +3% AND 미국 평균 > +3% | 단기 모멘텀·외국인 수급 유입 가능성 강조 분석 |
| `외부충격_하락` | SOX < -3% AND 미국 평균 < -3% | 하방 리스크·외국인 수급 이탈 가능성 강조 분석 |

시나리오 타입은 `PipelineState.scenario_type`에 저장되어 이후 `request_llm`, `generate_report` 노드까지 전파된다.

### Case D — 멀티종목 컨텍스트 구성

`build_context` 노드에서 메인 종목(삼성전자) 외에 국내·미국 참고 종목의 시장 데이터를 컨텍스트 블록으로 구성하여, LLM이 업종 전반의 흐름을 참고할 수 있게 한다.

| 컨텍스트 블록 | 대상 종목 | 포함 정보 |
|--------------|-----------|-----------|
| `domestic_context` | 한미반도체 (042700), 제주반도체 (TBD), SK하이닉스 (000660) | 종목명, 등락률, 거래량 |
| `us_context` | NVDA, AMD, INTC, AVGO, QCOM + ^SOX | 종목별 등락률, SOX 지수 변동 |

두 컨텍스트 블록은 LLM 프롬프트의 user 메시지에 메인 종목 데이터 + RAG 검색 결과와 함께 포함된다.

### LLM 프롬프트 구조

`build_messages()` 함수가 시나리오와 재시도 상태에 따라 프롬프트를 구성한다.

| 메시지 | 구성 |
|--------|------|
| **system** | 기본 분석 지시 + JSON 출력 형식 + (Case C) 시나리오별 추가 지시 + (Case B 2차 재시도) Few-shot 예시 |
| **user** | 메인 종목 OHLCV + RAG 검색 결과 + 국내 참고 종목 동향 + 미국 반도체 동향 + 시나리오 타입 + 예측 날짜 |

LLM 응답은 아래 JSON 형식으로 강제된다:

```json
{
  "ticker": "005930",
  "date": "2026-03-07",
  "prediction": "상승 | 하락 | 횡보",
  "confidence_score": 8,
  "scenario_type": "일반",
  "bull_case": "강세 근거",
  "bear_case": "약세 근거",
  "key_references": ["참고자료1", "참고자료2"],
  "evidence_count": 5
}

---

## 파일럿 대상 종목

> 종목 목록은 `config/tickers.json`으로 외부 관리.

| 구분 | 종목 | 티커 |
|------|------|------|
| 메인 예측 종목 | 삼성전자 | 005930 |
| 국내 참고 종목 | 한미반도체, 제주반도체, SK하이닉스 | 042700, TBD, 000660 |
| 미국 참고 종목 | NVIDIA, AMD, Intel, Broadcom, Qualcomm | NVDA, AMD, INTC, AVGO, QCOM |
| 미국 지수 | PHLX 반도체 지수 (SOX) | ^SOX |

---

## 데이터 수집 소스

> 소스 설정은 `config/data_sources.json`으로 관리.

| 소스 ID | 설명 | 라이브러리 | 주기 |
|---------|------|-----------|------|
| `krx_ohlcv` | 국내 주가 OHLCV (30일) | FinanceDataReader / pykrx | 1일 2회 |
| `krx_investor` | 투자자별 순매수 동향 (7일) | pykrx | 1일 2회 |
| `dart_disclosure` | 기업 공시 (사업/반기/주요사항) | DART API | 1일 2회 |
| `dart_financial` | 연결 재무제표 | DART API | 분기 |
| `naver_news` | 종목 뉴스 (최대 20건) | BeautifulSoup | 1일 2회 |
| `us_price` | 미국 반도체 주가 (전일 종가) | yfinance | 1일 1회 |
| `sox_index` | SOX 지수 (전일 종가) | yfinance | 1일 1회 |
| `pdf_files` | PDF 리포트 파일 목록 | pathlib | 1일 2회 |

---

## 기술 스택

| 영역 | 기술 | 전략 키 |
|------|------|---------|
| 국내 주가 수집 | FinanceDataReader, pykrx | — |
| 미국 주가/지수 수집 | yfinance | — |
| 뉴스/공시 크롤링 | BeautifulSoup, DART API | — |
| PDF 로딩 | pdfplumber / pymupdf / pdfminer / PyPDF2 | `--pdf-engine` |
| 청킹 | LangChain TextSplitter, kss, tiktoken | `--strategy` |
| 임베딩 모델 | BAAI/bge-m3 / Upstage Solar / OpenAI text-embedding | `--embed-strategy` |
| 벡터 DB | Chroma (로컬) / Pinecone (클라우드) | `--store-strategy` |
| LLM | Claude claude-sonnet-4-6 / GPT-4o / Gemini 2.0 Flash | `--llm-strategy` |
| 오케스트레이션 | LangGraph StateGraph | — |
| 리포트 발송 | Slack Incoming Webhook + Block Kit | — |
| CI/CD | GitHub Actions (lint + Docker build + 스케줄 + 배포) | — |
| 컨테이너 | Docker + docker-compose | — |
| 언어 | Python 3.11 | — |

---

## 빠른 시작

### 1. 환경 설정

```bash
cp .env.example .env
# .env 에 필요한 API 키 입력 (사용하는 전략에 해당하는 키만 필요)

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 전체 파이프라인 실행

```bash
# 수집 → 로딩 → 청킹 → 임베딩 → 벡터DB → RAG 예측 → 오케스트레이션 → Slack 발송
python3 -m src.main --all
```

### 3. 단계별 실행

```bash
python3 -m src.main --collect          # 데이터 수집
python3 -m src.main --load             # 텍스트 로딩
python3 -m src.main --chunk            # 청킹
python3 -m src.main --embed            # 임베딩
python3 -m src.main --store            # 벡터DB 저장
python3 -m src.main --predict          # RAG + LLM 예측
python3 -m src.main --orchestrate      # LangGraph 오케스트레이션
python3 -m src.main --notify           # Slack 발송
```

각 단계는 이전 결과 파일이 존재하면 자동으로 건너뛴다. 강제 재실행:

```bash
python3 -m src.main --collect --force-collect
python3 -m src.main --chunk --force-chunk
python3 -m src.main --embed --force-embed
python3 -m src.main --store --force-store
python3 -m src.main --predict --force-predict
python3 -m src.main --orchestrate --force-orchestrate
```

### 4. 전략 변경

```bash
# PDF 엔진
python3 -m src.main --load --pdf-engine pymupdf

# 청킹 전략
python3 -m src.main --chunk --strategy sentence
python3 -m src.main --chunk --strategy token

# 임베딩 전략
python3 -m src.main --embed --embed-strategy upstage
python3 -m src.main --embed --embed-strategy openai

# 벡터DB 전략
python3 -m src.main --store --store-strategy pinecone

# LLM 전략
python3 -m src.main --orchestrate --llm-strategy openai
python3 -m src.main --orchestrate --llm-strategy gemini
```

CLI 인자가 없으면 `config/pipeline.json`의 기본값이 적용된다.

### 5. 기타 옵션

```bash
# 특정 수집 폴더 지정
python3 -m src.main --load 2026_0308_18

# 디버그 로그 활성화
python3 -m src.main --all --debug

# 전체 강제 재실행
python3 -m src.main --all --force-collect --force-load --force-chunk --force-embed --force-store --force-predict --force-orchestrate
```

### 6. Docker로 실행

```bash
# 이미지 빌드 + 전체 파이프라인 실행
docker compose up --build

# 단계별 실행
docker compose run --rm stock-pipeline python -m src.main --collect
docker compose run --rm stock-pipeline python -m src.main --orchestrate
```

---

## 프로젝트 구조

```
stock_prediction_plan/
├── README.md                       # 프로젝트 개요 (현재 파일)
├── CICD-Policy.md                  # CI/CD 정책 문서
├── LICENSE
├── Dockerfile                      # Python 3.11 slim + torch CPU
├── docker-compose.yml              # 볼륨/환경변수 포함 실행 설정
├── requirements.txt                # Python 의존성
├── .env.example                    # 환경 변수 템플릿
├── .dockerignore
├── .gitignore
│
├── .github/workflows/
│   ├── ci.yml                      # push/PR → ruff lint + Docker 빌드 + Slack 알림
│   ├── cd.yml                      # staging push → SSH 배포 + Slack 알림
│   └── schedule.yml                # 평일 18:00 KST 전체 파이프라인 자동 실행
│
├── config/
│   ├── pipeline.json               # 파이프라인 전략 설정 (PDF/청킹/임베딩/LLM/벡터DB)
│   ├── tickers.json                # 종목 관리 (메인/국내참고/미국참고/지수)
│   └── data_sources.json           # 데이터 수집 소스 및 재시도 정책
│
├── docs/
│   ├── 01_data_collection.md       # 데이터 수집 설계
│   ├── 02_chunking.md              # 청킹 설계
│   ├── 03_embedding.md             # 임베딩 설계
│   ├── 04_vector_db.md             # 벡터 DB 설계
│   ├── 05_langchain.md             # RAG + LLM 예측 설계
│   ├── 06_langgraph.md             # LangGraph 오케스트레이션 설계
│   └── 07_report_slack.md          # 리포트 & Slack 발송 설계
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # CLI 진입점 (argparse + 단계별 실행)
│   ├── settings.py                 # 환경 변수 로더 (.env)
│   ├── logger.py                   # 중앙 로깅 (콘솔 + 파일 RotatingFileHandler)
│   └── pipeline/
│       ├── __init__.py
│       ├── collection/             # Phase 1: 데이터 수집
│       │   ├── collector.py        #   ThreadPoolExecutor 병렬 수집
│       │   ├── config_loader.py    #   config JSON 로더
│       │   ├── fetchers.py         #   소스별 fetcher 구현
│       │   ├── models.py           #   TickerConfig, DataSourceConfig 등
│       │   └── main.py             #   수집 단독 실행용
│       ├── loading/                # Phase 2: 텍스트 로딩
│       │   ├── loader.py           #   로딩 오케스트레이터
│       │   ├── pdf_loader.py       #   PDF 엔진 통합 로더
│       │   ├── dart_doc_loader.py  #   DART 공시 문서 로더
│       │   ├── url_loader.py       #   URL 텍스트 로더
│       │   ├── models.py           #   LoadedDocument 모델
│       │   └── snapshot.py         #   loaded_docs.json 관리
│       ├── chunking/               # Phase 3: 청킹 (전략 패턴)
│       │   ├── base.py             #   ChunkStrategy ABC
│       │   ├── chunker.py          #   청킹 오케스트레이터
│       │   ├── models.py           #   ChunkedDocument 모델
│       │   ├── snapshot.py         #   chunks.json 관리
│       │   └── strategies/
│       │       ├── fixed.py        #     고정 크기 + 오버랩
│       │       ├── recursive.py    #     구분자 재귀 분할 (LangChain)
│       │       ├── sentence.py     #     한국어 문장 단위 (kss)
│       │       └── token.py        #     토큰 단위 (tiktoken)
│       ├── embedding/              # Phase 4: 임베딩 (전략 패턴)
│       │   ├── base.py             #   EmbeddingStrategy ABC
│       │   ├── embedder.py         #   임베딩 오케스트레이터
│       │   ├── models.py           #   EmbeddedChunk 모델
│       │   ├── snapshot.py         #   embeddings.json 관리
│       │   └── strategies/
│       │       ├── bge.py          #     BAAI/bge-m3 (로컬, 무료)
│       │       ├── upstage.py      #     Upstage Solar Embedding API
│       │       └── openai.py       #     OpenAI text-embedding API
│       ├── vectordb/               # Phase 5: 벡터DB (전략 패턴)
│       │   ├── base.py             #   VectorDBStrategy ABC
│       │   ├── store.py            #   upsert/search 오케스트레이터
│       │   ├── models.py           #   SearchResult 모델
│       │   ├── snapshot.py         #   vectordb_meta.json 관리
│       │   └── strategies/
│       │       ├── chroma.py       #     Chroma (로컬 파일 기반)
│       │       └── pinecone.py     #     Pinecone (관리형 클라우드)
│       ├── rag/                    # Phase 6: RAG + LLM 예측 (전략 패턴)
│       │   ├── base.py             #   LLMStrategy ABC
│       │   ├── predictor.py        #   예측 오케스트레이터
│       │   ├── context.py          #   컨텍스트 빌더 (시나리오 감지 포함)
│       │   ├── prompt.py           #   프롬프트 메시지 빌더
│       │   ├── models.py           #   PredictionOutput 모델
│       │   ├── snapshot.py         #   prediction_result.json 관리
│       │   └── strategies/
│       │       ├── claude.py       #     Claude claude-sonnet-4-6
│       │       ├── openai.py       #     GPT-4o
│       │       └── gemini.py       #     Gemini 2.0 Flash
│       ├── orchestration/          # Phase 7: LangGraph 오케스트레이션
│       │   ├── graph.py            #   StateGraph 빌드 + 컴파일
│       │   ├── nodes.py            #   노드 함수 구현 (7개 노드)
│       │   ├── state.py            #   PipelineState TypedDict
│       │   ├── runner.py           #   실행기 (run_pipeline / run_and_save)
│       │   └── snapshot.py         #   orchestration_result.json 관리
│       └── notification/           # Phase 8: Slack 발송
│           ├── __init__.py
│           └── slack.py            #   Block Kit 포맷팅 + Webhook 전송
│
├── collected_datas/                # 수집 결과 (YYYY_MMDD_HH/ 폴더별)
├── chroma_db/                      # Chroma 벡터DB 로컬 저장소
└── logs/                           # 로그 파일 (YYYY_MMDD.log, 10MB 로테이션)
```

---

## 설정 파일

### `config/pipeline.json`

모든 파이프라인 전략의 기본값을 관리. CLI 인자가 있으면 override 된다.

| 섹션 | 기본 전략 | 선택 가능 전략 |
|------|-----------|---------------|
| `loading.pdf_engine` | `pdfplumber` | pymupdf, pdfminer, pypdf2, auto |
| `chunking.strategy` | `recursive` | sentence, token, fixed |
| `embedding.strategy` | `bge` | upstage, openai |
| `vectordb.strategy` | `chroma` | pinecone |
| `llm.strategy` | `openai` | claude, gemini |

### `config/tickers.json`

종목 목록 관리. `active: false`로 개별 비활성화 가능.

### `config/data_sources.json`

수집 소스 정의 + 재시도 정책 (최대 3회, 30초 간격, 최종 실패 시 전일 데이터 사용).

---

## 환경 변수

`.env.example`을 `.env`로 복사 후 사용하는 전략에 해당하는 키를 설정한다.

| 변수 | 용도 | 필수 여부 |
|------|------|-----------|
| `DART_API_KEY` | DART OpenAPI (공시/재무제표) | 수집 단계 |
| `OPENAI_API_KEY` | OpenAI 임베딩/LLM | openai 전략 사용 시 |
| `ANTHROPIC_API_KEY` | Claude LLM | claude 전략 사용 시 |
| `GOOGLE_API_KEY` | Gemini LLM | gemini 전략 사용 시 |
| `UPSTAGE_API_KEY` | Upstage Solar 임베딩 | upstage 전략 사용 시 |
| `PINECONE_API_KEY` | Pinecone 벡터DB | pinecone 전략 사용 시 |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook | 발송 단계 |

---

## CI/CD

### 브랜치 전략

| 브랜치 | 용도 |
|--------|------|
| `main` | 프로덕션 |
| `staging` | 스테이징 (push 시 자동 배포) |
| `develop` | 개발 |

### 워크플로우

| 파일 | 트리거 | 작업 |
|------|--------|------|
| `ci.yml` | push/PR (main, staging, develop) | ruff lint → Docker 빌드 검증 → Slack 알림 |
| `cd.yml` | staging push | SSH 배포 → docker compose 재시작 → Slack 알림 |
| `schedule.yml` | 평일 09:00 UTC (18:00 KST) | Docker 빌드 → 전체 파이프라인 실행 (`--all`) |

`schedule.yml`은 `workflow_dispatch`로 수동 실행도 가능하며, `extra_args` 입력으로 추가 인자를 전달할 수 있다.

---

## 로깅

- **포맷**: `시각 [레벨] 모듈.함수명:줄번호 — 메시지`
- **출력**: 콘솔 + `logs/YYYY_MMDD.log`
- **로테이션**: 파일당 10MB, 최대 7개 백업
- **디버그 모드**: `--debug` 플래그로 DEBUG 레벨 활성화

---

## 개발 로드맵

| Phase | 내용 | 관련 문서 | 상태 |
|-------|------|-----------|------|
| Phase 1 | 데이터 수집 파이프라인 | 01_data_collection.md | ✅ 완료 |
| Phase 2 | 텍스트 로딩 + 청킹 | 02_chunking.md | ✅ 완료 |
| Phase 3 | 임베딩 + 벡터DB | 03_embedding.md, 04_vector_db.md | ✅ 완료 |
| Phase 4 | RAG + LLM 예측 (3-way 전략) | 05_langchain.md | ✅ 완료 |
| Phase 5 | LangGraph 오케스트레이션 | 06_langgraph.md | ✅ 완료 |
| Phase 6 | Slack 리포트 발송 | 07_report_slack.md | ✅ 완료 |
| Phase 7 | CI/CD 자동화 (GitHub Actions + Docker) | CICD-Policy.md | ✅ 완료 |
| Phase 8 | 예측 정확도 평가 및 프롬프트 튜닝 | — | 미착수 |

---

## 리스크 및 고려사항

- **한국어 임베딩 성능:** 공시/뉴스 텍스트 특성상 한국어 특화 모델 벤치마크 필수
- **미국-국내 시차:** 미국장 마감(한국시간 새벽) → 수집 타이밍 설계 주의
- **SOX 임계값 조정:** ±3% 기준은 파일럿 운영 후 실제 데이터 기반으로 재검토
- **API 비용:** LLM 재시도 최대 3회 → 일일 호출량 모니터링 필요
- **예측 면책:** 본 시스템의 예측은 투자 권고가 아니며 참고 목적으로만 활용
