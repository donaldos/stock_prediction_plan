# 주가 지표 예측 리포트 자동화 시스템

> **버전:** v1.3 | **작성일:** 2026-03-08 | **상태:** 구현 완료

---

## 프로젝트 개요

특정 시간에 스케줄러가 자동 실행되어, 지정 종목의 당일 주가 지표를 예측하는 리포트를 생성하고 슬랙으로 발송하는 AI 기반 자동화 파이프라인.

---

## 전체 아키텍처

```
[스케줄러: 오전 8~9시 / 오후 4~5시]
    │
    ▼
[01. 데이터 수집] ── 국내 주가, 뉴스/공시, 재무제표, 미국 반도체 주가/SOX
    │
    ▼
[02. 데이터 로딩 + 청킹] ── PDF/JSON 텍스트 추출 → 분할
    │
    ▼
[03. 임베딩] ────── 텍스트 → 벡터 변환 (BGE / Upstage / OpenAI)
    │
    ▼
[04. 벡터 DB] ───── 벡터 저장 및 검색 (Chroma / Pinecone)
    │
    ▼
[05. RAG + LLM] ─── 관련 청크 검색 → 예측 요청 (Claude / GPT-4o / Gemini)
    │
    ▼
[06. LangGraph] ─── 시나리오 분기 / 응답 검증 / 재시도 (최대 3회)
    │
    ▼
[07. Slack 발송] ── Block Kit 리포트 → Incoming Webhook 전송
```

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

## 스케줄링

| 실행 시점 | 작업 내용 |
|-----------|-----------|
| 오전 8~9시 | 전일 종가 + 미국장 마감 데이터 수집 → 당일 예측 리포트 생성 및 슬랙 발송 |
| 오후 4~5시 | 당일 종가 수집 → 익일 예측용 데이터 갱신 + 당일 예측 정확도 피드백 |

---

## 기술 스택 요약

| 영역 | 기술 | 상태 |
|------|------|------|
| 국내 주가 수집 | FinanceDataReader, pykrx | 확정 |
| 미국 주가/지수 수집 | yfinance | 확정 |
| 뉴스/공시 크롤링 | BeautifulSoup, DART API | 확정 |
| PDF 로딩 | pdfplumber / pymupdf / pdfminer / PyPDF2 | 확정 |
| 청킹 | LangChain TextSplitter (recursive / sentence / token / fixed) | 확정 |
| 임베딩 모델 | BAAI/bge-m3 (기본) / Upstage Solar / OpenAI text-embedding | 확정 |
| 벡터 DB | Chroma (로컬, 기본) / Pinecone (클라우드) | 확정 |
| LLM | Claude claude-sonnet-4-6 / GPT-4o / Gemini 2.0 Flash | 확정 |
| RAG 오케스트레이션 | 전략 패턴 직접 구현 (LangChain 미사용) | 확정 |
| 시나리오 분기 | LangGraph StateGraph | 확정 |
| 리포트 발송 | Slack Incoming Webhook + Block Kit | 확정 |
| 스케줄러 | GitHub Actions (cron) | 확정 |
| 언어 | Python 3.9+ | 확정 |

---

## 빠른 시작

### 1. 환경 설정

```bash
cp .env.example .env
# .env 에 API 키 입력
pip install -r requirements.txt
```

### 2. 전체 파이프라인 실행

```bash
# 수집 → 로딩 → 청킹 → 임베딩 → 벡터DB → 오케스트레이션 → Slack 발송
python3 -m src.main --all
```

### 3. 단계별 실행

```bash
python3 -m src.main --collect          # 데이터 수집
python3 -m src.main --load             # 텍스트 로딩
python3 -m src.main --chunk            # 청킹
python3 -m src.main --embed            # 임베딩
python3 -m src.main --store            # 벡터DB 저장
python3 -m src.main --orchestrate      # LangGraph 예측
python3 -m src.main --notify           # Slack 발송
```

### 4. Docker로 실행

```bash
# 이미지 빌드 + 전체 파이프라인 실행
docker compose up --build

# 단계별 실행
docker compose run --rm stock-pipeline python -m src.main --collect
docker compose run --rm stock-pipeline python -m src.main --orchestrate
```

### 5. LLM / 임베딩 전략 변경

```bash
# LLM 전략 변경 (config/pipeline.json 또는 CLI)
python3 -m src.main --orchestrate --llm-strategy openai
python3 -m src.main --orchestrate --llm-strategy gemini

# 임베딩 전략 변경
python3 -m src.main --embed --embed-strategy upstage
```

---

## 문서 구조

```
project/
├── README.md                  # 프로젝트 개요 + 전체 아키텍처 (현재 파일)
├── Dockerfile                 # 컨테이너 이미지 빌드
├── docker-compose.yml         # 볼륨/환경변수 포함 실행 설정
├── .github/
│   └── workflows/
│       ├── ci.yml             # push/PR 시 lint + Docker 빌드 검증 + Slack 알림
│       └── schedule.yml       # 평일 18:00 KST 전체 파이프라인 자동 실행
├── docs/
│   ├── 01_data_collection.md  # 데이터 수집
│   ├── 02_chunking.md         # 청킹
│   ├── 03_embedding.md        # 임베딩
│   ├── 04_vector_db.md        # 벡터 DB
│   ├── 05_langchain.md        # RAG + LLM 예측
│   ├── 06_langgraph.md        # LangGraph 오케스트레이션
│   └── 07_report_slack.md     # 리포트 & Slack 발송
├── config/
│   ├── pipeline.json          # 파이프라인 전략 설정
│   ├── tickers.json           # 종목 관리
│   └── data_sources.json      # 데이터 소스 관리
└── src/
    ├── main.py                # 실행 진입점
    ├── settings.py            # 환경 변수 로더
    └── pipeline/
        ├── collection/        # Phase 1: 데이터 수집
        ├── loading/           # Phase 2: 텍스트 로딩
        ├── chunking/          # Phase 2: 청킹
        ├── embedding/         # Phase 3: 임베딩
        ├── vectordb/          # Phase 4: 벡터DB
        ├── rag/               # Phase 5: RAG + LLM
        ├── orchestration/     # Phase 6: LangGraph
        └── notification/      # Phase 7: Slack 발송
```

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
| Phase 7 | 예측 정확도 평가 및 프롬프트 튜닝 | 전체 | 미착수 |
| Phase 8 | 스케줄러 연동 자동화 (GitHub Actions + Docker) | — | ✅ 완료 |

---

## 리스크 및 고려사항

- **한국어 임베딩 성능:** 공시/뉴스 텍스트 특성상 한국어 특화 모델 벤치마크 필수
- **미국-국내 시차:** 미국장 마감(한국시간 새벽) → 수집 타이밍 설계 주의
- **SOX 임계값 조정:** ±3% 기준은 파일럿 운영 후 실제 데이터 기반으로 재검토
- **API 비용:** LLM 재시도 최대 3회 → 일일 호출량 모니터링 필요
- **예측 면책:** 본 시스템의 예측은 투자 권고가 아니며 참고 목적으로만 활용
