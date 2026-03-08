# 01. 데이터 수집 / 로딩 (Data Collection & Loading)

> **관련 Phase:** Phase 1 | **상태:** 구현 완료

---

## 개요

스케줄러 실행 시 국내외 주가 데이터, 뉴스/공시, 재무제표, PDF를 수집하는 모듈.
수집된 데이터는 텍스트 로딩 → 청킹(02) → 임베딩(03) → 벡터DB(04) 파이프라인으로 전달된다.

---

## 폴더 구조

```
src/pipeline/
├── collection/               # 수집 단계
│   ├── __init__.py
│   ├── collector.py          # 수집 오케스트레이터 (ThreadPoolExecutor 병렬)
│   ├── config_loader.py      # tickers.json / data_sources.json 로더
│   ├── fetchers.py           # 소스별 fetcher 함수들
│   └── models.py             # TickerConfig, DataSourceConfig, DataSource 등
└── loading/                  # 텍스트 로딩 단계
    ├── __init__.py
    ├── loader.py             # 로딩 오케스트레이터 (ThreadPoolExecutor 병렬)
    ├── url_loader.py         # 네이버 뉴스 본문 수집
    ├── dart_doc_loader.py    # DART 공시 본문 수집
    ├── pdf_loader.py         # PDF 텍스트 추출 (다중 엔진)
    ├── snapshot.py           # loaded_docs.json 저장/로드 유틸
    └── models.py             # Document 데이터 클래스

config/
├── tickers.json              # 종목 관리
└── data_sources.json         # 수집 항목·소스·스케줄·재시도 정책

collected_datas/
└── YYYY_MMDD_HH/             # 시간대별 수집 결과 폴더
    ├── krx_ohlcv.json
    ├── us_price.json
    ├── sox_index.json
    ├── naver_news.json
    ├── dart_disclosure.json
    ├── dart_financial.json
    ├── pdf_files.json
    └── loaded_docs.json      # 텍스트 로딩 스냅샷
```

---

## 수집 항목 및 소스

> 수집 항목·소스·재시도 정책은 `config/data_sources.json`으로 외부 관리.
> 종목 목록은 `config/tickers.json` 참조.

| id | 수집 항목 | 라이브러리 | 수집 주기 | 시장 |
|----|-----------|------------|-----------|------|
| `krx_ohlcv` | 국내 주가 OHLCV | FinanceDataReader (fallback: pykrx) | daily_2x | KRX |
| `dart_disclosure` | 기업 공시 | DART OpenAPI | daily_2x | KRX |
| `naver_news` | 뉴스 | BeautifulSoup | daily_2x | KRX |
| `dart_financial` | 재무제표 | DART OpenAPI | quarterly | KRX |
| `us_price` | 미국 반도체 주가 | yfinance | daily_1x | NASDAQ |
| `sox_index` | SOX 지수 | yfinance | daily_1x | INDEX |
| `pdf_files` | PDF 파일 | 로컬 디렉토리 스캔 | on_demand | — |

---

## 데이터 흐름

```
[python3 -m src.main --collect]
    │
    ├── config 로드 (tickers.json + data_sources.json)
    │
    ├── ThreadPoolExecutor (max_workers=5) — 병렬 수집
    │   ├── krx_ohlcv.json
    │   ├── us_price.json
    │   ├── sox_index.json
    │   ├── naver_news.json
    │   ├── dart_disclosure.json
    │   ├── dart_financial.json
    │   └── pdf_files.json
    │
    └── collected_datas/YYYY_MMDD_HH/ 저장

[python3 -m src.main --load]
    │
    ├── 스냅샷 캐시 확인 (loaded_docs.json 존재 시 건너뜀)
    │
    ├── ThreadPoolExecutor — 병렬 로딩
    │   ├── naver_news   → HTML 파싱 → list[Document]
    │   ├── dart         → DART API 호출 → list[Document]
    │   └── pdf          → PDF 텍스트 추출 → list[Document]
    │
    ├── 결과 병합 (news → dart → pdf 순서 보장)
    └── loaded_docs.json 스냅샷 저장
```

---

## CLI 사용법

```bash
# 수집 (현재 시간대 폴더에 데이터 있으면 자동 건너뜀)
python3 -m src.main --collect

# 수집 강제 재실행
python3 -m src.main --collect --force-collect

# 로딩 (스냅샷 있으면 자동 건너뜀)
python3 -m src.main --load

# 특정 폴더 로딩
python3 -m src.main --load 2026_0307_07

# PDF 엔진 지정
python3 -m src.main --load --pdf-engine pymupdf

# 로딩 강제 재실행
python3 -m src.main --load --force-load

# 수집 + 로딩 전체
python3 -m src.main --all
```

---

## 스냅샷 캐시 메커니즘

각 단계는 결과를 JSON으로 저장하며, 이미 존재하면 재실행 없이 캐시를 사용한다.

| 단계 | 캐시 파일 | 강제 재실행 플래그 |
|------|-----------|-------------------|
| 수집 | `YYYY_MMDD_HH/*.json` (소스별) | `--force-collect` |
| 로딩 | `loaded_docs.json` | `--force-load` |

```python
# snapshot.py 인터페이스 (loading 단계)
snapshot.save(documents, path, meta)   # Document 리스트 저장
snapshot.load(path)                    # Document 리스트 복원
snapshot.exists(path)                  # 유효한 스냅샷 존재 여부
snapshot.summary(path)                 # 로그용 요약 문자열
```

---

## 병렬 처리

수집 단계와 로딩 단계 모두 `ThreadPoolExecutor`로 병렬 실행.

| 단계 | 병렬 단위 | 적합 이유 |
|------|-----------|-----------|
| 수집 | 소스 단위 (최대 5개 동시) | 네트워크 I/O bound |
| 로딩 | 로더 단위 (news / dart / pdf 동시) | 네트워크 + 파일 I/O bound |

---

## PDF 로딩 엔진

`pdf_loader.py`는 엔진을 선택적으로 사용할 수 있다.

| engine | 라이브러리 | 특징 |
|--------|------------|------|
| `pdfplumber` | pdfplumber | 기본값, 표 추출 강점 |
| `pymupdf` | PyMuPDF | 속도 빠름 |
| `pdfminer` | pdfminer.six | 텍스트 레이아웃 정밀 |
| `pypdf2` | PyPDF2 | 경량 |
| `auto` | — | 위 순서로 폴백 시도 |

```bash
python3 -m src.main --load --pdf-engine pymupdf
```

---

## 로깅

모든 단계는 `logging` 모듈을 통해 소스별 경과 시간을 기록한다.

```
수집중 — source_id=naver_news
수집 완료 — source_id=naver_news  elapsed=4.87s
전체 수집 완료 — 저장 위치=...  total_elapsed=5.12s

로딩중 — naver_news
naver_news 로딩 완료 — 42건  elapsed=3.21s
전체 로딩 완료 — total=87  total_elapsed=3.45s
```

로그 파일: `logs/YYYY_MMDD.log` (RotatingFileHandler, 10MB, 7일 보관)

---

## 데이터 모델

```python
@dataclass
class Document:
    text: str           # 추출된 본문 텍스트
    source: str         # 출처 URL / 파일 경로
    source_type: str    # "naver_news" | "dart_disclosure" | "pdf"
    metadata: dict      # 날짜, 제목, 티커 등 부가 정보
```

---

## 기술 스택

| 라이브러리 | 용도 | 설치 |
|------------|------|------|
| `FinanceDataReader` | 국내 주가 수집 | `pip install finance-datareader` |
| `pykrx` | KRX 주가 보완 수집 | `pip install pykrx` |
| `yfinance` | 미국 주가 / SOX 지수 | `pip install yfinance` |
| `requests` | DART API 호출 | 기본 내장 |
| `beautifulsoup4` | 뉴스 크롤링 | `pip install beautifulsoup4` |
| `pdfplumber` | PDF 텍스트 추출 (기본) | `pip install pdfplumber` |
| `pymupdf` | PDF 추출 대안 | `pip install pymupdf` |
| `python-dotenv` | 환경 변수 관리 | `pip install python-dotenv` |

---

## 미결 사항 (TBD)

- [ ] 제주반도체 티커 확인 및 `tickers.json` 업데이트
- [ ] 미국 파일럿 5종목 최종 확정
- [ ] 네이버 금융 크롤링 셀렉터 설계 (`naver_news` HTML 구조 파악)
- [ ] DART API 키 발급 및 `.env` 환경변수 관리 방식 확정
- [ ] `dart_disclosure` params.report_types 최종 확정
- [ ] `data_sources.json` quarterly 스케줄 트리거 조건 상세 정의
- [ ] DART API 속도 제한 대응 (max_workers 조정)
