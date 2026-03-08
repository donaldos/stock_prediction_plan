"""
config/*.json 파일을 읽어 데이터 모델로 변환하는 로더.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import (
    Ticker,
    TickerConfig,
    DataSource,
    DataSourceConfig,
    RetryPolicy,
)


@dataclass
class PipelineConfig:
    """
    config/pipeline.json 에서 로드되는 파이프라인 전략 설정.

    각 단계의 기본 전략과 파라미터를 정의한다.
    CLI 인자가 명시된 경우 이 값을 override 한다.

    Attributes:
        pdf_engine:         PDF 로딩 엔진 (기본값)
        chunk_strategy:     청킹 전략 이름 (기본값)
        chunk_params:       현재 chunk_strategy 에 대응하는 파라미터
        all_chunk_params:   전략별 파라미터 전체 {strategy: params} — CLI override 시 사용
        embed_strategy:     임베딩 전략 이름 (기본값)
        embed_params:       현재 embed_strategy 에 대응하는 파라미터
        all_embed_params:   전략별 파라미터 전체 {strategy: params} — CLI override 시 사용
        vectordb_strategy:  벡터DB 전략 이름 (기본값)
        vectordb_collection: 기본 컬렉션(네임스페이스) 이름
        vectordb_params:    현재 vectordb_strategy 에 대응하는 파라미터
        all_vectordb_params: 전략별 파라미터 전체 — CLI override 시 사용
        search_top_k:       기본 Top-K 검색 수
        search_top_k_expanded: RAG 재시도 시 확장 Top-K
    """
    pdf_engine:           str
    chunk_strategy:       str
    chunk_params:         dict = field(default_factory=dict)
    all_chunk_params:     dict = field(default_factory=dict)
    embed_strategy:       str  = "bge"
    embed_params:         dict = field(default_factory=dict)
    all_embed_params:     dict = field(default_factory=dict)
    vectordb_strategy:    str  = "chroma"
    vectordb_collection:  str  = "stock_rag"
    vectordb_params:      dict = field(default_factory=dict)
    all_vectordb_params:  dict = field(default_factory=dict)
    search_top_k:         int  = 5
    search_top_k_expanded: int = 10
    llm_strategy:         str  = "claude"
    llm_ticker:           str  = "005930"
    llm_params:           dict = field(default_factory=dict)
    all_llm_params:       dict = field(default_factory=dict)

    def chunk_params_for(self, strategy: str) -> dict:
        """특정 청킹 전략의 파라미터 반환 (CLI override 시 사용)."""
        return self.all_chunk_params.get(strategy, {})

    def embed_params_for(self, strategy: str) -> dict:
        """특정 임베딩 전략의 파라미터 반환 (CLI override 시 사용)."""
        return self.all_embed_params.get(strategy, {})

    def vectordb_params_for(self, strategy: str) -> dict:
        """특정 벡터DB 전략의 파라미터 반환 (CLI override 시 사용)."""
        return self.all_vectordb_params.get(strategy, {})

    def llm_params_for(self, strategy: str) -> dict:
        """특정 LLM 전략의 파라미터 반환 (CLI override 시 사용)."""
        return self.all_llm_params.get(strategy, {})

# 프로젝트 루트 기준 config 디렉터리
_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def load_tickers(path: Path | None = None) -> TickerConfig:
    """
    tickers.json을 읽어 TickerConfig로 반환.

    Args:
        path: 파일 경로 (기본값: config/tickers.json)
    """
    fpath = path or _CONFIG_DIR / "tickers.json"
    with open(fpath, encoding="utf-8") as f:
        raw = json.load(f)

    return TickerConfig(
        main=[Ticker.from_dict(t) for t in raw["main"]],
        domestic_reference=[Ticker.from_dict(t) for t in raw["domestic_reference"]],
        us_reference=[Ticker.from_dict(t) for t in raw["us_reference"]],
        us_index=[Ticker.from_dict(t) for t in raw["us_index"]],
    )


def load_data_sources(path: Path | None = None) -> DataSourceConfig:
    """
    data_sources.json을 읽어 DataSourceConfig로 반환.

    Args:
        path: 파일 경로 (기본값: config/data_sources.json)
    """
    fpath = path or _CONFIG_DIR / "data_sources.json"
    with open(fpath, encoding="utf-8") as f:
        raw = json.load(f)

    return DataSourceConfig(
        sources=[DataSource.from_dict(s) for s in raw["sources"]],
        schedule_definitions=raw["schedule_definitions"],
        retry_policy=RetryPolicy.from_dict(raw["retry_policy"]),
    )


def load_pipeline_config(path: Path | None = None) -> PipelineConfig:
    """
    pipeline.json 을 읽어 PipelineConfig 로 반환.

    params 는 전략별 딕셔너리 구조 {strategy: {param: value}} 이며,
    현재 선택된 전략의 params 를 chunk_params / embed_params 에 매핑한다.

    Args:
        path: 파일 경로 (기본값: config/pipeline.json)
    """
    fpath = path or _CONFIG_DIR / "pipeline.json"
    with open(fpath, encoding="utf-8") as f:
        raw = json.load(f)

    chunk_strategy = raw["chunking"]["strategy"]
    all_chunk_params = {
        k: v for k, v in raw["chunking"].get("params", {}).items()
        if not k.startswith("_")
    }

    embed_strategy = raw["embedding"]["strategy"]
    all_embed_params = {
        k: v for k, v in raw["embedding"].get("params", {}).items()
        if not k.startswith("_")
    }

    vdb_section = raw.get("vectordb", {})
    vectordb_strategy = vdb_section.get("strategy", "chroma")
    all_vectordb_params = {
        k: v for k, v in vdb_section.get("params", {}).items()
        if not k.startswith("_")
    }
    search_section = vdb_section.get("search", {})

    llm_section = raw.get("llm", {})
    llm_strategy = llm_section.get("strategy", "claude")
    all_llm_params = {
        k: v for k, v in llm_section.get("params", {}).items()
        if not k.startswith("_")
    }

    return PipelineConfig(
        pdf_engine=raw["loading"]["pdf_engine"],
        chunk_strategy=chunk_strategy,
        chunk_params=all_chunk_params.get(chunk_strategy, {}),
        all_chunk_params=all_chunk_params,
        embed_strategy=embed_strategy,
        embed_params=all_embed_params.get(embed_strategy, {}),
        all_embed_params=all_embed_params,
        vectordb_strategy=vectordb_strategy,
        vectordb_collection=vdb_section.get("collection", "stock_rag"),
        vectordb_params=all_vectordb_params.get(vectordb_strategy, {}),
        all_vectordb_params=all_vectordb_params,
        search_top_k=search_section.get("top_k", 5),
        search_top_k_expanded=search_section.get("top_k_expanded", 10),
        llm_strategy=llm_strategy,
        llm_ticker=llm_section.get("ticker", "005930"),
        llm_params=all_llm_params.get(llm_strategy, {}),
        all_llm_params=all_llm_params,
    )


def load_all(
    tickers_path: Path | None = None,
    sources_path: Path | None = None,
) -> tuple[TickerConfig, DataSourceConfig]:
    """
    tickers.json + data_sources.json 을 한 번에 로드.

    Returns:
        (TickerConfig, DataSourceConfig) 튜플
    """
    return load_tickers(tickers_path), load_data_sources(sources_path)
