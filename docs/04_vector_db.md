# 04. 벡터 DB (Vector Database)

> **관련 Phase:** Phase 4 | **상태:** 구현 완료 (Chroma 기본 / Pinecone 선택)

---

## 개요

임베딩된 벡터와 메타데이터를 벡터DB에 저장(upsert)하고,
RAG 검색 시 유사 청크를 반환하는 파이프라인 단계.

- **기본 전략:** Chroma (로컬, 영속 저장)
- **선택 전략:** Pinecone (클라우드, 병렬 upsert)
- 전략은 `config/pipeline.json`에서 선택하고, CLI `--store-strategy`로 override 가능

---

## 파일 구조

```
src/pipeline/vectordb/
├── __init__.py            # 공개 API: VectorStore, upsert_and_save, search_similar, SearchResult
├── base.py                # VectorDBStrategy ABC
├── models.py              # SearchResult 데이터 모델
├── snapshot.py            # vectordb_meta.json 저장/확인/요약
├── store.py               # VectorStore, upsert_and_save, search_similar
└── strategies/
    ├── __init__.py
    ├── chroma.py          # ChromaStrategy (로컬 PersistentClient)
    └── pinecone.py        # PineconeStrategy (클라우드, 병렬 배치)
```

---

## 기술 스택

| 라이브러리 | 전략 | 설치 |
|------------|------|------|
| `chromadb` | `chroma` (기본) | `pip install chromadb` |
| `pinecone` | `pinecone` (선택) | `pip install pinecone` |

> `langchain`은 사용하지 않음 — 직접 chromadb/pinecone 클라이언트 호출

---

## 설계

### 전략 패턴 (Strategy Pattern)

```python
class VectorDBStrategy(ABC):
    @abstractmethod
    def upsert(self, embedded_chunks: list[EmbeddedChunk], collection: str) -> int: ...

    @abstractmethod
    def search(
        self,
        query_vector: list[float],
        collection: str,
        top_k: int = 5,
        filter_meta: dict | None = None,
    ) -> list[SearchResult]: ...

    @property @abstractmethod
    def name(self) -> str: ...

    @property @abstractmethod
    def params(self) -> dict: ...
```

| 전략 | 클래스 | 특징 |
|------|--------|------|
| `chroma` | `ChromaStrategy` | 로컬 PersistentClient, cosine 유사도 |
| `pinecone` | `PineconeStrategy` | 클라우드, namespace 분리, 병렬 upsert |

---

### SearchResult 데이터 모델

```python
@dataclass
class SearchResult:
    text:        str           # 청크 원문
    source:      str           # 소스 파일명
    source_type: str           # 데이터 타입 (news, financial 등)
    score:       float         # 유사도 점수 (0.0 ~ 1.0)
    metadata:    dict          # 기타 메타데이터
```

---

### Chroma 전략 (`strategies/chroma.py`)

```python
class ChromaStrategy(VectorDBStrategy):
    def __init__(self, persist_dir: str = "chroma_db"):
        self._persist_dir = persist_dir
        self._client = None  # 지연 초기화

    @property
    def _col_client(self):
        if self._client is None:
            root = Path(__file__).resolve().parents[5]
            self._client = chromadb.PersistentClient(
                path=str(root / self._persist_dir)
            )
        return self._client
```

- **chunk_id**: `MD5(source + str(chunk_index))` — upsert 멱등성 보장
- **거리 → 유사도**: cosine distance `d` → `1.0 - d`
- **컬렉션**: `collection` 파라미터 = Chroma 컬렉션명

---

### Pinecone 전략 (`strategies/pinecone.py`)

```python
class PineconeStrategy(VectorDBStrategy):
    def __init__(self, index_name: str = "stock-rag", max_concurrent: int = 4):
        self._index_name = index_name
        self._max_concurrent = max_concurrent
        self._index = None  # 지연 초기화
```

- **네임스페이스**: `collection` 파라미터 = Pinecone namespace
- **병렬 upsert**: `ThreadPoolExecutor(max_workers=max_concurrent)`, 배치 100개
- **환경 변수**: `PINECONE_API_KEY` 필요

---

### 스냅샷 패턴 (`snapshot.py`)

임베딩 스냅샷(벡터 JSON 저장)과 달리, 벡터DB는 자체적으로 데이터를 영속 관리한다.
`vectordb_meta.json`에는 **메타데이터만** 저장한다.

```json
{
  "strategy":      "chroma",
  "collection":    "stock_rag",
  "params":        { "persist_dir": "chroma_db" },
  "total_upserted": 1024,
  "source_count":  12,
  "saved_at":      "2026-03-07T10:30:00"
}
```

| 함수 | 역할 |
|------|------|
| `save(path, meta)` | vectordb_meta.json 저장 |
| `exists(path)` | 파일 존재 여부 확인 |
| `summary(path)` | 로그용 요약 문자열 반환 |

> `load()` 없음 — 벡터 데이터는 DB가 직접 관리

---

## Config (`config/pipeline.json`)

```json
"vectordb": {
  "strategy": "chroma",
  "collection": "stock_rag",
  "search": {
    "top_k": 5,
    "top_k_expanded": 10
  },
  "params": {
    "chroma":   { "persist_dir": "chroma_db" },
    "pinecone": { "index_name": "stock-rag", "max_concurrent": 4 }
  }
}
```

- `strategy`: 사용할 벡터DB 전략 (`chroma` | `pinecone`)
- `collection`: Chroma=컬렉션명, Pinecone=네임스페이스명
- `params`: 전략별 파라미터 (전략 교체 시 해당 키의 params 자동 선택)
- `search.top_k`: 기본 Top-K 검색 수
- `search.top_k_expanded`: RAG 재시도 시 확장 Top-K

---

## 실행 방법

```bash
# 기본 실행 (chroma, config 기본값 사용)
python3 -m src.main --store

# 전략 지정
python3 -m src.main --store --store-strategy chroma
python3 -m src.main --store --store-strategy pinecone

# 강제 재저장 (vectordb_meta.json 있어도 재실행)
python3 -m src.main --store --force-store

# 전체 파이프라인 (수집 → 로딩 → 청킹 → 임베딩 → 벡터DB)
python3 -m src.main --all
```

### 스킵 조건

`{run_dir}/vectordb_meta.json`이 존재하면 자동으로 건너뜀.
`--force-store` 플래그로 강제 재실행 가능.

---

## 공개 API (`src/pipeline/vectordb/__init__.py`)

```python
from src.pipeline.vectordb import VectorStore, upsert_and_save, search_similar, SearchResult

# upsert
upsert_and_save(run_dir, strategy="chroma", collection="stock_rag")

# 검색 (query_vector는 사전에 임베딩된 벡터)
results = search_similar(
    query_vector=[...],
    strategy="chroma",
    collection="stock_rag",
    top_k=5,
)
for r in results:
    print(r.score, r.text[:80])
```

---

## Top-K 검색 전략

| 상황 | Top-K | 설정 위치 |
|------|-------|-----------|
| 기본 검색 | 5 | `pipeline.json > vectordb.search.top_k` |
| RAG 재시도 (범위 확장) | 10 | `pipeline.json > vectordb.search.top_k_expanded` |

---

## 환경 변수

| 변수 | 전략 | 설명 |
|------|------|------|
| `PINECONE_API_KEY` | `pinecone` | Pinecone API 키 |

> Chroma 전략은 API 키 불필요 (로컬 파일 기반)

---

## 저장 메타데이터 필드

청크 upsert 시 함께 저장되는 메타데이터:

| 필드 | 설명 |
|------|------|
| `source` | 소스 파일명 |
| `source_type` | 데이터 타입 (news, financial, disclosure 등) |
| `chunk_index` | 청크 순번 |
| `total_chunks` | 해당 소스의 전체 청크 수 |
| `model` | 사용된 임베딩 모델명 |

> `ticker`, `market` 등 종목 정보는 현재 chunk 메타데이터에서 source 파싱으로 추출 가능 (향후 명시적 필드 추가 검토)

---

## 향후 과제

- [ ] 벡터 업데이트 정책 — 매일 upsert vs 전체 재색인 결정
- [ ] 오래된 벡터 삭제 정책 — 보관 기간 정의
- [ ] Pinecone 이전 시 마이그레이션 스크립트
- [ ] 종목별 컬렉션 분리 운용 (`collection=ticker_code`)
- [ ] filter_meta 활용 — source_type, date 범위 필터 검색
