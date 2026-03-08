"""
데이터 수집 모듈 데이터 모델 정의.
config/*.json 을 읽어 변환된 결과의 타입을 정의한다.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────
# tickers.json 관련 모델
# ──────────────────────────────────────────

@dataclass
class Ticker:
    ticker: str
    name: str
    market: str
    active: bool
    sector: Optional[str] = None
    note: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Ticker":
        return cls(
            ticker=d["ticker"],
            name=d["name"],
            market=d["market"],
            active=d.get("active", True),
            sector=d.get("sector"),
            note=d.get("note"),
        )


@dataclass
class TickerConfig:
    main: list[Ticker]
    domestic_reference: list[Ticker]
    us_reference: list[Ticker]
    us_index: list[Ticker]

    def active_kr(self) -> list[Ticker]:
        """국내 활성 종목 (main + domestic_reference)"""
        return [t for t in self.main + self.domestic_reference if t.active]

    def active_us(self) -> list[Ticker]:
        """미국 활성 종목"""
        return [t for t in self.us_reference if t.active]

    def active_index(self) -> list[Ticker]:
        """활성 지수"""
        return [t for t in self.us_index if t.active]


# ──────────────────────────────────────────
# data_sources.json 관련 모델
# ──────────────────────────────────────────

@dataclass
class RetryPolicy:
    max_retries: int
    interval_seconds: int
    on_final_failure: str
    on_no_fallback: str

    @classmethod
    def from_dict(cls, d: dict) -> "RetryPolicy":
        return cls(
            max_retries=d["max_retries"],
            interval_seconds=d["interval_seconds"],
            on_final_failure=d["on_final_failure"],
            on_no_fallback=d["on_no_fallback"],
        )


@dataclass
class DataSource:
    id: str
    label: str
    type: str
    library: str
    market: str
    schedule: str
    active: bool
    params: dict = field(default_factory=dict)
    fallback_library: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "DataSource":
        return cls(
            id=d["id"],
            label=d["label"],
            type=d["type"],
            library=d["library"],
            market=d["market"],
            schedule=d["schedule"],
            active=d.get("active", True),
            params=d.get("params", {}),
            fallback_library=d.get("fallback_library"),
        )


@dataclass
class DataSourceConfig:
    sources: list[DataSource]
    schedule_definitions: dict[str, str]
    retry_policy: RetryPolicy

    def active_sources(self) -> list[DataSource]:
        """활성화된 소스만 반환"""
        return [s for s in self.sources if s.active]

    def get_source(self, source_id: str) -> Optional[DataSource]:
        """id로 소스 조회"""
        return next((s for s in self.sources if s.id == source_id), None)
