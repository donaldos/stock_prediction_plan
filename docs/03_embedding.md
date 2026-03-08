# 03. 데이터 임베딩 (Embedding)

> **관련 Phase:** Phase 2 | **상태:** 구현 완료

---

## 개요

청킹된 `Chunk` 리스트를 벡터로 변환하는 모듈.
전략 패턴(Strategy Pattern) 기반으로 임베딩 모델을 런타임에 교체할 수 있다.
변환된 `EmbeddedChunk` 리스트는 벡터DB(04) 단계로 전달된다.

> 임베딩 전략은 `config/pipeline.json` 에서 관리하며, CLI 인자로 일회성 override 가능.

---

## 폴더 구조

```
src/pipeline/embedding/
├── __init__.py           # 공개 인터페이스 (EmbeddedChunk, Embedder, embed_and_save 등)
├── base.py               # EmbeddingStrategy 추상 인터페이스
├── models.py             # EmbeddedChunk 데이터 클래스
├── embedder.py           # Embedder 위임 클래스 + embed_and_save + load_embeddings
├── snapshot.py           # embeddings.json 저장/로드 유틸
└── strategies/
    ├── __init__.py
    ├── bge.py            # BgeEmbedder — BAAI/bge-m3 로컬 임베딩 (기본)
    ├── upstage.py        # UpstageEmbedder — Upstage Solar Embedding API
    └── openai.py         # OpenAIEmbedder — OpenAI text-embedding-3-small API
```

---

## 데이터 흐름

```
chunks.json
    │
    └── load_chunks(run_dir) → list[Chunk]
            │
            └── Embedder.embed_all(chunks) → list[EmbeddedChunk]
                    │
                    └── embed_and_save(run_dir) → embeddings.json
```

```bash
# 임베딩 실행 (embeddings.json 있으면 자동 건너뜀)
python3 -m src.main --embed

# 전략 지정 (pipeline.json override)
python3 -m src.main --embed --embed-strategy bge
python3 -m src.main --embed --embed-strategy upstage
python3 -m src.main --embed --embed-strategy openai

# 강제 재임베딩
python3 -m src.main --embed --force-embed
```

---

## 전략 패턴 구조

```
EmbeddingStrategy (추상)
    ├── embed(texts) -> list[list[float]]   # 텍스트 리스트 → 벡터 리스트
    ├── name: str                           # 전략 이름
    ├── model_name: str                     # 사용 모델명
    └── dimension: int                      # 벡터 차원 수

Embedder (위임 클래스)
    ├── __init__(strategy, **kwargs)        # 전략 선택 및 생성
    ├── embed_all(chunks) -> list[EmbeddedChunk]
    └── strategy_name / model_name / dimension (프로퍼티)
```

새 전략 추가 시:
1. `strategies/` 에 클래스 작성 (`EmbeddingStrategy` 상속)
2. `embedder.py`의 `_STRATEGY_REGISTRY` 에 등록
3. `strategies/__init__.py` export 추가
4. `config/pipeline.json` 의 `embedding.params` 에 해당 전략 파라미터 추가

---

## 임베딩 전략 상세

| 전략 | 클래스 | 모델 | 차원 | API 키 | 병렬화 | 적합한 상황 |
|------|--------|------|------|--------|--------|-------------|
| `bge` (기본) | `BgeEmbedder` | BAAI/bge-m3 | 1024 | 불필요 | 내부 배치 최적화 | 비용 없이 고품질, 로컬 GPU/CPU |
| `upstage` | `UpstageEmbedder` | solar-embedding-1-large | 4096 | `UPSTAGE_API_KEY` | `ThreadPoolExecutor` | 한국어 특화 고품질 |
| `openai` | `OpenAIEmbedder` | text-embedding-3-small | 1536 | `OPENAI_API_KEY` | `ThreadPoolExecutor` | 다국어, 범용 |

### 병렬 처리 방식

| 전략 | 방식 | 파라미터 |
|------|------|----------|
| `bge` | `sentence-transformers` 내부 배치 처리 (PyTorch 최적화) | `batch_size` |
| `upstage` | 배치 API 요청을 `ThreadPoolExecutor` 로 동시 발송 | `batch_size`, `max_concurrent` |
| `openai` | 동일 | `batch_size`, `max_concurrent` |

> `max_concurrent` 를 올리면 속도가 빨라지지만 API rate limit 초과 위험 있음.
> Upstage 무료 티어 기준 `max_concurrent: 1~2` 권장.

---

## 데이터 모델

```python
@dataclass
class EmbeddedChunk:
    text: str              # 원본 청크 텍스트
    source: str            # 원본 출처 (URL / 파일 경로)
    source_type: str       # "naver_news" | "dart_disclosure" | "pdf"
    chunk_index: int       # 동일 Document 내 청크 순번 (0-based)
    total_chunks: int      # 동일 Document 의 전체 청크 수
    metadata: dict         # 청킹 메타 + 임베딩 전략 정보
    embedding: list[float] # 임베딩 벡터
    model: str             # 사용한 모델명
```

`metadata` 예시:
```json
{
  "title": "삼성전자 1분기 실적 발표",
  "date": "2026-03-07",
  "chunk_strategy": "recursive",
  "embedding_strategy": "bge",
  "embedding_model": "BAAI/bge-m3",
  "embedding_dim": 1024
}
```

---

## 전략 설정 (config/pipeline.json)

전략 선택과 파라미터를 외부에서 관리한다.
전략별로 파라미터가 다르므로 전략 키 기반 구조를 사용한다.

```json
"embedding": {
  "strategy": "bge",
  "params": {
    "bge":     { "batch_size": 32 },
    "upstage": { "batch_size": 50,  "max_concurrent": 4 },
    "openai":  { "batch_size": 512, "max_concurrent": 8 }
  }
}
```

CLI override 시 해당 전략의 `params` 가 자동으로 선택된다.

---

## 스냅샷 캐시 메커니즘

| 단계 | 캐시 파일 | 강제 재실행 플래그 |
|------|-----------|-------------------|
| 임베딩 | `embeddings.json` | `--force-embed` |

```python
# snapshot.py 인터페이스 (embedding 단계)
snapshot.save(embedded_chunks, path, meta)   # EmbeddedChunk 리스트 저장
snapshot.load(path)                          # EmbeddedChunk 리스트 복원
snapshot.exists(path)                        # 유효한 스냅샷 존재 여부
snapshot.summary(path)                       # 로그용 요약 문자열
```

`embeddings.json` 구조:
```json
{
  "snapshot_at": "2026-03-07T10:30:00",
  "run_dir": "collected_datas/2026_0307_07",
  "strategy": "bge",
  "model": "BAAI/bge-m3",
  "dimension": 1024,
  "strategy_params": { "batch_size": 32 },
  "source_chunks": 312,
  "total": 312,
  "counts": { "naver_news": 210, "dart_disclosure": 80, "pdf": 22 },
  "embedded_chunks": [ ... ]
}
```

---

## 로깅

임베딩 및 저장 단계별 경과 시간을 기록한다.

```
청크 로드 완료 — 312개 Chunk
임베딩 시작 — strategy=bge model=BAAI/bge-m3 dim=1024 params={'batch_size': 32}
bge-m3 모델 로딩 중 — BAAI/bge-m3
bge-m3 모델 로딩 완료
임베딩 완료 — total=312 counts={...}  embed_elapsed=12.34s  save_elapsed=0.21s
```

캐시 사용 시:
```
캐시 사용 — 기존 임베딩 결과 로드: total=312 (...)  strategy=bge  model=BAAI/bge-m3  저장시각=2026-03-07T10:30:00
```

---

## 사용 예시 (코드)

```python
from src.pipeline.embedding import Embedder, embed_and_save, load_embeddings
from pathlib import Path

# 직접 임베딩
embedder = Embedder("bge", batch_size=32)
embedded = embedder.embed_all(chunks)

# 파이프라인 함수 (캐시 포함)
run_dir = Path("collected_datas/2026_0307_07")
output = embed_and_save(run_dir, strategy="upstage")

# 다음 단계에서 로드
embedded_chunks = load_embeddings(run_dir)
```

---

## 기술 스택

| 라이브러리 | 용도 | 설치 |
|------------|------|------|
| `sentence-transformers` | `bge` 전략 — BAAI/bge-m3 로컬 실행 | `pip install sentence-transformers` |
| `openai` | `upstage` / `openai` 전략 — API 호출 | `pip install openai` |

---

## 파이프라인 단계 간 연결

```
[청킹 단계]              [임베딩 단계]             [벡터DB 단계]
chunks.json  →  load_chunks()  →  Embedder  →  embeddings.json  →  load_embeddings()
list[Chunk]                       embed_all()   list[EmbeddedChunk]
```

다운스트림(`vectordb/`)에서 임베딩을 로드하는 방법:
```python
from src.pipeline.embedding import load_embeddings
embedded_chunks = load_embeddings(run_dir)   # embeddings.json → list[EmbeddedChunk]
```

---

## 미결 사항 (TBD)

- [ ] 최적 임베딩 모델 벤치마크 (한국어 뉴스/공시 샘플 100건 기준 Top-5 Recall 비교)
- [ ] bge vs upstage 품질 비교 실험
- [ ] 동일 텍스트 재임베딩 방지 — 청크 해시 기반 캐싱 검토
- [ ] API rate limit 초과 시 자동 재시도 (tenacity 등)
- [ ] GPU 가용 시 bge 자동 device 선택 검증 (`device=None` → cuda/mps 자동)
