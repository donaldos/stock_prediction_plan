"""
src/pipeline/embedding — 전략 패턴 기반 임베딩 모듈.

데이터 연결 흐름:
    chunks.json
      └─ load_chunks(run_dir)  →  list[Chunk]
            └─ Embedder.embed_all(chunks)  →  list[EmbeddedChunk]
                  └─ embed_and_save(run_dir)  →  embeddings.json

전략 선택:
    Embedder("bge",     batch_size=32)               ← 기본, 로컬, 무료
    Embedder("upstage", batch_size=50)               ← Upstage API 필요
    Embedder("openai",  model="text-embedding-3-small")  ← OpenAI API 필요
"""

from .models import EmbeddedChunk
from .base import EmbeddingStrategy
from .embedder import Embedder, embed_and_save, load_embeddings
from .strategies import BgeEmbedder, UpstageEmbedder, OpenAIEmbedder
from . import snapshot

__all__ = [
    "EmbeddedChunk",
    "EmbeddingStrategy",
    "Embedder",
    "embed_and_save",
    "load_embeddings",
    "snapshot",
    "BgeEmbedder",
    "UpstageEmbedder",
    "OpenAIEmbedder",
]
