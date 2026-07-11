from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from trading_bot.backtest.runner import BacktestRunner, load_historical_csv
from trading_bot.data.mt5_history import (
    MT5HistoryError,
    export_paginated_from_local_terminal,
    export_range_from_local_terminal,
)
from trading_bot.journal.paper_forward import PaperForwardJournal
from trading_bot.research.edge_v2_feature_separation import (
    analyze_feature_separation,
    load_journal_records,
    write_feature_separation_report,
)


def run_edge_v2_mt5_research(
    *,
    symbol: str,
    timeframe: str,
    start: str,
    end: str,
    out_dir: str | Path,
    history_mode: str = "range",
    page_size: int = 5_000,
    include_current_bar: bool = False,
    require_complete: bool = True,
    gateway: Any | None = None,
) -> dict[str, Any]:
    """Export local MT5 candles and run a read-only Edge V2 research workflow."""
    output_dir = Path(out_dir)
    candles_path = output_dir / "mt5_history.csv"
    manifest_path = output_dir / "mt5_history_manifest.json"
    logs_dir = output_dir / "journal"
    report_path = output_dir / "edge_v2_feature_separation.json"

    if history_mode == "range":
        exported_path = export_range_from_local_terminal(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            output=candles_path,
            manifest_out=manifest_path,
            gateway=gateway,
        )
        pagination_manifest_path = manifest_path
    elif history_mode == "paginated":
        export = export_paginated_from_local_terminal(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            output=candles_path,
            manifest_out=manifest_path,
            page_size=page_size,
            include_current_bar=include_current_bar,
            require_complete=require_complete,
            gateway=gateway,
        )
        exported_path = export.csv_path
        pagination_manifest_path = export.manifest_path
    else:
        raise ValueError("history_mode must be range or paginated")
    candles = load_historical_csv(exported_path)
    journal = PaperForwardJournal(logs_dir)
    BacktestRunner(
        symbol=symbol,
        timeframe=timeframe,
        journal=journal,
    ).run(candles)

    journal_path = logs_dir / "trades.jsonl"
    records = load_journal_records(journal_path) if journal_path.exists() else []
    report = analyze_feature_separation(records)
    winner_count = sum(float(record.get("pnl", 0)) > 0 for record in records)
    loser_count = sum(float(record.get("pnl", 0)) < 0 for record in records)
    report.update(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "date_range": {"start": start, "end": end},
            "history_mode": history_mode,
            "data_provider": "mt5",
            "candle_count": len(candles),
            "trade_count": len(records),
            "winner_count": winner_count,
            "loser_count": loser_count,
            "breakeven_count": len(records) - winner_count - loser_count,
            "sample_size_warning": min(winner_count, loser_count) < 10,
            "submit_allowed": False,
            "broker_api_called": False,
            "strongest_separating_features": rank_feature_separation(
                report["features"]
            )[0],
            "weakest_separating_features": rank_feature_separation(
                report["features"]
            )[1],
        }
    )
    write_feature_separation_report(report, report_path)
    return {
        "candles_path": exported_path,
        "manifest_path": pagination_manifest_path,
        "journal_path": journal_path,
        "report_path": report_path,
        "report": report,
    }


def rank_feature_separation(features: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    scored = [
        (feature, abs(float(result["simple_effect_size"])))
        for feature, result in features.items()
        if result.get("simple_effect_size") is not None
    ]
    strongest = [feature for feature, _ in sorted(scored, key=lambda item: (-item[1], item[0]))]
    weakest = [feature for feature, _ in sorted(scored, key=lambda item: (item[1], item[0]))]
    return strongest, weakest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a diagnostic-only Edge V2 research pipeline from local MT5 history"
    )
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", choices=["M5", "M15", "H1", "H4"], default="M5")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--history-mode", choices=["range", "paginated"], default="range")
    parser.add_argument("--page-size", type=int, default=5_000)
    parser.add_argument("--include-current-bar", action="store_true")
    parser.add_argument("--allow-partial-history", action="store_true")
    args = parser.parse_args()
    try:
        result = run_edge_v2_mt5_research(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start=args.start,
            end=args.end,
            out_dir=args.out_dir,
            history_mode=args.history_mode,
            page_size=args.page_size,
            include_current_bar=args.include_current_bar,
            require_complete=not args.allow_partial_history,
        )
    except MT5HistoryError as exc:
        raise SystemExit(f"environment_blocked: {exc}") from exc
    print(result["report_path"])


if __name__ == "__main__":
    main()
