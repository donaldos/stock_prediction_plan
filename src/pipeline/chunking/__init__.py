"""
src/chunking — 전략 패턴 기반 청킹 모듈.

데이터 연결 흐름:
    loaded_docs.json
      └─ load_snapshot(run_dir)  →  list[Document]
            └─ Chunker.chunk_all(docs)  →  list[Chunk]
                  └─ chunk_and_save(run_dir)  →  chunks.json

전략 선택:
    Chunker("fixed",     chunk_size=500, overlap=50)
    Chunker("recursive", chunk_size=500, overlap=50)   ← 기본
    Chunker("sentence",  sentences_per_chunk=5, overlap=1)
    Chunker("token",     chunk_tokens=256, overlap=32)
"""

from .models import Chunk
from .base import ChunkStrategy
from .chunker import Chunker, chunk_and_save, load_chunks
from .strategies import FixedSizeChunker, RecursiveChunker, SentenceChunker, TokenChunker
from . import snapshot

__all__ = [
    "Chunk",
    "ChunkStrategy",
    "Chunker",
    "chunk_and_save",
    "load_chunks",
    "snapshot",
    "FixedSizeChunker",
    "RecursiveChunker",
    "SentenceChunker",
    "TokenChunker",
]
