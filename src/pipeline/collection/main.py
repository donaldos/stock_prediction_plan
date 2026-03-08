"""
실행 스크립트.

  config 검증만:  python -m src.data_collection.main
  실제 수집 실행: python -m src.data_collection.main --collect
"""

from __future__ import annotations
import sys
from .config_loader import load_all
from .collector import collect_and_save


def main() -> None:
    tickers, sources = load_all()

    # ── tickers.json 검증 ──────────────────────────────────────
    print("=" * 50)
    print("[tickers.json]")
    print("=" * 50)

    sections = {
        "main":               tickers.main,
        "domestic_reference": tickers.domestic_reference,
        "us_reference":       tickers.us_reference,
        "us_index":           tickers.us_index,
    }
    for section, items in sections.items():
        print(f"\n  [{section}]")
        for t in items:
            status = "O" if t.active else "X"
            note = f"  ※ {t.note}" if t.note else ""
            print(f"    [{status}] {t.ticker:>8}  {t.name} ({t.market}){note}")

    print(f"\n  활성 국내 종목: {[t.ticker for t in tickers.active_kr()]}")
    print(f"  활성 미국 종목: {[t.ticker for t in tickers.active_us()]}")
    print(f"  활성 지수:      {[t.ticker for t in tickers.active_index()]}")

    # ── data_sources.json 검증 ─────────────────────────────────
    print()
    print("=" * 50)
    print("[data_sources.json]")
    print("=" * 50)

    print(f"\n  재시도 정책: 최대 {sources.retry_policy.max_retries}회 "
          f"/ {sources.retry_policy.interval_seconds}초 간격 "
          f"/ 최종실패→{sources.retry_policy.on_final_failure}")

    print("\n  수집 소스:")
    for s in sources.sources:
        status = "O" if s.active else "X"
        fallback = f" (fallback: {s.fallback_library})" if s.fallback_library else ""
        schedule_desc = sources.schedule_definitions.get(s.schedule, s.schedule)
        print(f"    [{status}] {s.id:<20} {s.library}{fallback}")
        print(f"           schedule : {schedule_desc}")
        if s.params:
            clean_params = {k: v for k, v in s.params.items() if k != "note"}
            if clean_params:
                print(f"           params   : {clean_params}")

    print(f"\n  활성 소스 id: {[s.id for s in sources.active_sources()]}")
    print()

    # ── 수집 실행 (--collect 플래그 시) ────────────────────────
    if "--collect" in sys.argv:
        print("=" * 50)
        print("[수집 실행]")
        print("=" * 50)
        collect_and_save(tickers, sources)


if __name__ == "__main__":
    main()
