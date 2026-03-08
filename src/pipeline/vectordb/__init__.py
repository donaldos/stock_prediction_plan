"""
src/pipeline/vectordb — 전략 패턴 기반 벡터DB 모듈.

데이터 연결 흐름:
    embeddings.json
      └─ load_embeddings(run_dir)  →  list[EmbeddedChunk]
            └─ VectorStore.upsert_all(chunks, collection)  →  int
                  └─ upsert_and_save(run_dir)  →  vectordb_meta.json

전략 선택:
    VectorStore("chroma",   persist_dir="chroma_db")   ← 기본, 로컬, 무료
    VectorStore("pinecone", index_name="stock-rag")    ← 관리형 클라우드
"""

from .models import SearchResult
from .base import VectorDBStrategy
from .store import VectorStore, upsert_and_save, search_similar
from .strategies import ChromaStrategy, PineconeStrategy
from . import snapshot

__all__ = [
    "SearchResult",
    "VectorDBStrategy",
    "VectorStore",
    "upsert_and_save",
    "search_similar",
    "snapshot",
    "ChromaStrategy",
    "PineconeStrategy",
]
