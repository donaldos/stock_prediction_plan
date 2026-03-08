# 02. 데이터 청킹 (Chunking)

> **관련 Phase:** Phase 2 | **상태:** 구현 완료

---

## 개요

로딩된 `Document` 리스트를 LLM 컨텍스트 윈도우에 적합한 크기로 분할하는 모듈.
전략 패턴(Strategy Pattern) 기반으로 청킹 방식을 런타임에 교체할 수 있다.
청킹된 `Chunk` 리스트는 임베딩(03) 단계로 전달된다.

> 주가 수치 데이터(OHLCV)는 청킹 불필요 — 직접 프롬프트 컨텍스트로 주입.

---

## 폴더 구조

```
src/pipeline/chunking/
├── __init__.py           # 공개 인터페이스 (Chunk, Chunker, chunk_and_save 등)
├── base.py               # ChunkStrategy 추상 인터페이스
├── models.py             # Chunk 데이터 클래스
├── chunker.py            # Chunker 위임 클래스 + chunk_and_save + load_chunks
├── snapshot.py           # chunks.json 저장/로드 유틸
└── strategies/
    ├── __init__.py
    ├── fixed.py          # FixedSizeChunker — 고정 길이 분할
    ├── recursive.py      # RecursiveChunker — 재귀 구분자 분할 (기본)
    ├── sentence.py       # SentenceChunker — 문장 단위 분할 (kss)
    └── token.py          # TokenChunker — 토큰 단위 분할 (tiktoken)
```

---

## 데이터 흐름

```
loaded_docs.json
    │
    └── load_snapshot(run_dir) → list[Document]
            │
            └── Chunker.chunk_all(docs) → list[Chunk]
                    │
                    └── chunk_and_save(run_dir) → chunks.json
```

```bash
# 청킹 실행 (chunks.json 있으면 자동 건너뜀)
python3 -m src.main --chunk

# 전략 지정
python3 -m src.main --chunk --strategy recursive
python3 -m src.main --chunk --strategy sentence
python3 -m src.main --chunk --strategy token
python3 -m src.main --chunk --strategy fixed

# 강제 재청킹
python3 -m src.main --chunk --force-chunk
```

---

## 전략 패턴 구조

```
ChunkStrategy (추상)
    ├── split(text) -> list[str]   # 텍스트 → 분할 결과
    ├── name: str                  # 전략 이름
    └── params: dict               # 전략 파라미터

Chunker (위임 클래스)
    ├── __init__(strategy, **kwargs)   # 전략 선택 및 생성
    ├── chunk(document) -> list[Chunk]
    └── chunk_all(documents) -> list[Chunk]
```

새 전략 추가 시:
1. `strategies/` 에 클래스 작성 (`ChunkStrategy` 상속)
2. `chunker.py`의 `_STRATEGY_REGISTRY` 에 등록
3. `strategies/__init__.py` export 추가

---

## 청킹 전략 상세

| 전략 | 클래스 | 핵심 파라미터 | 의존 라이브러리 | 적합한 데이터 |
|------|--------|---------------|-----------------|---------------|
| `fixed` | `FixedSizeChunker` | `chunk_size=500`, `overlap=50` | 없음 (순수 Python) | 구조가 없는 긴 텍스트 |
| `recursive` | `RecursiveChunker` | `chunk_size=500`, `overlap=50` | `langchain-text-splitters` | 뉴스, 공시 (기본값) |
| `sentence` | `SentenceChunker` | `sentences_per_chunk=5`, `overlap=1` | `kss` (한국어 문장 분리) | 한국어 문장 중심 텍스트 |
| `token` | `TokenChunker` | `chunk_tokens=256`, `overlap=32` | `tiktoken` | LLM 토큰 한도 정밀 제어 |

`recursive` 전략의 한국어+영문 구분자 순서:
```python
["\n\n", "\n", ".", "。", "!", "？", "?", " ", ""]
```

---

## 데이터 모델

```python
@dataclass
class Chunk:
    text: str              # 청킹된 텍스트
    source: str            # 원본 출처 (URL / 파일 경로)
    source_type: str       # "naver_news" | "dart_disclosure" | "pdf"
    chunk_index: int       # 동일 Document 내 청크 순번 (0-based)
    total_chunks: int      # 동일 Document 의 전체 청크 수
    metadata: dict         # 원본 메타 + 청킹 전략 정보
```

`metadata` 예시:
```json
{
  "title": "삼성전자 1분기 실적 발표",
  "date": "2026-03-07",
  "chunk_strategy": "recursive",
  "chunk_chunk_size": 500,
  "chunk_overlap": 50
}
```

---

## 스냅샷 캐시 메커니즘

로딩 단계와 동일한 패턴으로 `snapshot.py`를 통해 관리한다.

| 단계 | 캐시 파일 | 강제 재실행 플래그 |
|------|-----------|-------------------|
| 청킹 | `chunks.json` | `--force-chunk` |

```python
# snapshot.py 인터페이스 (chunking 단계)
snapshot.save(chunks, path, meta)    # Chunk 리스트 저장
snapshot.load(path)                  # Chunk 리스트 복원
snapshot.exists(path)                # 유효한 스냅샷 존재 여부
snapshot.summary(path)               # 로그용 요약 문자열
```

`chunks.json` 구조:
```json
{
  "snapshot_at": "2026-03-07T09:15:00",
  "run_dir": "collected_datas/2026_0307_07",
  "strategy": "recursive",
  "strategy_params": {"chunk_size": 500, "overlap": 50},
  "source_docs": 87,
  "total": 312,
  "counts": {"naver_news": 210, "dart_disclosure": 80, "pdf": 22},
  "chunks": [ ... ]
}
```

---

## 로깅

청킹 및 저장 단계별 경과 시간을 기록한다.

```
스냅샷 로드 완료 — 87개 Document
청킹 시작 — strategy=recursive params={'chunk_size': 500, 'overlap': 50}
청킹 완료 — total=312 counts={...}  chunk_elapsed=0.18s  save_elapsed=0.05s
```

캐시 사용 시:
```
캐시 사용 — 기존 청킹 결과 로드: total=312 (...)  strategy=recursive  저장시각=2026-03-07T09:15:00
```

---

## 사용 예시 (코드)

```python
from src.pipeline.chunking import Chunker, chunk_and_save, load_chunks
from pathlib import Path

# 직접 청킹
chunker = Chunker("recursive", chunk_size=500, overlap=50)
chunks = chunker.chunk_all(documents)

# 파이프라인 함수 (캐시 포함)
run_dir = Path("collected_datas/2026_0307_07")
output = chunk_and_save(run_dir, strategy="sentence")

# 다음 단계에서 로드
chunks = load_chunks(run_dir)
```

---

## 기술 스택

| 라이브러리 | 용도 | 설치 |
|------------|------|------|
| `langchain-text-splitters` | `recursive` 전략 | `pip install langchain-text-splitters` |
| `kss` | `sentence` 전략 — 한국어 문장 분리 | `pip install kss` |
| `tiktoken` | `token` 전략 — OpenAI 토크나이저 | `pip install tiktoken` |

---

## 파이프라인 단계 간 연결

```
[로딩 단계]               [청킹 단계]              [임베딩 단계]
loaded_docs.json  →  load_snapshot()  →  Chunker  →  chunks.json  →  load_chunks()
list[Document]                            chunk_all()   list[Chunk]
```

다운스트림(`embedding/`)에서 청크를 로드하는 방법:
```python
from src.pipeline.chunking import load_chunks
chunks = load_chunks(run_dir)   # chunks.json → list[Chunk]
```

---

## 미결 사항 (TBD)

- [ ] 최적 청크 크기 실험 (500자 기준 → 임베딩 성능 테스트 후 조정)
- [ ] 재무제표 전용 청킹 전략 추가 (항목 단위 커스텀)
- [ ] 중복 청크 필터링 전략 (동일 기사 다수 수집 시)
- [ ] 청킹 품질 평가 기준 정의
- [ ] `kss` 미설치 시 폴백 동작 검증
