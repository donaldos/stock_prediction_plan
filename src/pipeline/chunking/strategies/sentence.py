"""
문장 단위 청킹 전략.

kss (Korean Sentence Splitter) 로 문장 분리 후
sentences_per_chunk 문장씩 묶는다.
kss 미설치 시 단순 줄바꿈/마침표 분리로 폴백한다.

의존성: kss (선택)  pip install kss
"""

from __future__ import annotations
import re
from ..base import ChunkStrategy


def _split_sentences_fallback(text: str) -> list[str]:
    """kss 없을 때 단순 문장 분리 (한국어 마침표 기준)."""
    raw = re.split(r"(?<=[.。!?！？])\s+", text)
    return [s.strip() for s in raw if s.strip()]


def _split_sentences_kss(text: str) -> list[str]:
    try:
        import kss
        return [s.strip() for s in kss.split_sentences(text) if s.strip()]
    except ImportError:
        return _split_sentences_fallback(text)


class SentenceChunker(ChunkStrategy):
    """
    문장 N개씩 묶어 청크 생성. overlap 은 문장 수 기준.

    Args:
        sentences_per_chunk: 청크당 문장 수 (기본 5)
        overlap:             오버랩 문장 수 (기본 1)
        use_kss:             True 이면 kss 사용, False 이면 폴백 분리기 사용
    """

    def __init__(
        self,
        sentences_per_chunk: int = 5,
        overlap: int = 1,
        use_kss: bool = True,
    ):
        if overlap >= sentences_per_chunk:
            raise ValueError("overlap 은 sentences_per_chunk 보다 작아야 합니다.")
        self._n = sentences_per_chunk
        self._overlap = overlap
        self._use_kss = use_kss

    @property
    def name(self) -> str:
        return "sentence"

    @property
    def params(self) -> dict:
        return {
            "sentences_per_chunk": self._n,
            "overlap": self._overlap,
            "use_kss": self._use_kss,
        }

    def split(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []

        sentences = (
            _split_sentences_kss(text)
            if self._use_kss
            else _split_sentences_fallback(text)
        )
        if not sentences:
            return [text]

        step = self._n - self._overlap
        chunks: list[str] = []
        start = 0
        while start < len(sentences):
            group = sentences[start: start + self._n]
            chunk = " ".join(group).strip()
            if chunk:
                chunks.append(chunk)
            start += step

        return chunks
