import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_bot.metrics.performance import calculate_performance_metrics


TRADE_FIELDS = (
    "trade_id",
    "timestamp_open",
    "timestamp_close",
    "symbol",
    "timeframe",
    "direction",
    "entry",
    "stop_loss",
    "take_profit",
    "exit_price",
    "pnl",
    "r_multiple",
    "outcome",
    "market_regime",
    "context_bias",
    "context_score",
    "context_reason",
    "entry_score",
    "distance_to_h1_high",
    "distance_to_h1_low",
    "distance_to_h1_mid",
)
OPTIONAL_TRADE_FIELDS = (
    "extension_atr",
    "spread",
    "spread_points",
    "point_size",
    "tick_size",
    "spread_price",
    "slippage_points",
    "slippage_price",
    "volatility",
    "atr",
    "candle_range",
    "risk_points",
    "reward_points",
    "planned_rr",
    "entry_distance_from_sweep",
    "bars_held",
    "exit_reason",
    "compression_score",
    "is_compressing",
    "range_duration_bars",
    "atr_contraction_pct",
    "recent_range_points",
    "prior_range_points",
    "pressure_score",
    "pressure_direction",
    "price_position_in_range",
    "upper_quartile_closes",
    "lower_quartile_closes",
    "average_pullback_depth",
)
OPTIONAL_BLOCKED_SETUP_FIELDS = (
    "blocked_by_quality_guard",
    "quality_block_reason",
    "extension_atr",
    "spread",
    "spread_points",
    "point_size",
    "tick_size",
    "spread_price",
    "slippage_points",
    "slippage_price",
    "entry_distance_from_sweep",
    "planned_rr",
    "volatility",
    "atr",
    "candle_range",
    "compression_score",
    "is_compressing",
    "range_duration_bars",
    "atr_contraction_pct",
    "recent_range_points",
    "prior_range_points",
    "pressure_score",
    "pressure_direction",
    "price_position_in_range",
    "upper_quartile_closes",
    "lower_quartile_closes",
    "average_pullback_depth",
)


class PaperForwardJournal:
    """Append-only JSONL journal for paper-forward observations."""

    def __init__(self, log_dir: str | Path = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.trades_path = self.log_dir / "trades.jsonl"
        self.setups_path = self.log_dir / "setups.jsonl"
        self.blocked_setups_path = self.log_dir / "blocked_setups.jsonl"
        self.post_cost_blocks_path = self.log_dir / "post_cost_blocks.jsonl"
        self.summary_path = self.log_dir / "daily_summary.json"

    def record_completed_trade(self, trade: dict[str, Any]) -> None:
        missing = [field for field in TRADE_FIELDS if field not in trade]
        if missing:
            raise ValueError(f"Missing completed trade fields: {', '.join(missing)}")
        if trade["outcome"] not in {"win", "loss", "breakeven"}:
            raise ValueError("outcome must be win, loss, or breakeven")
        payload = {field: trade[field] for field in TRADE_FIELDS}
        payload.update(
            {
                field: trade[field]
                for field in OPTIONAL_TRADE_FIELDS
                if field in trade
            }
        )
        self._append(self.trades_path, payload)

    def record_setup(self, recommendation: dict[str, Any]) -> None:
        if not recommendation.get("setup"):
            return
        blocked = bool(
            recommendation.get("blocked_by_context")
            or recommendation.get("blocked_by_entry_score")
            or recommendation.get("no_chase_blocked")
            or recommendation.get("blocked_by_quality_guard")
        )
        timestamp = str(
            recommendation.get("generated_at")
            or datetime.now(timezone.utc).isoformat()
        )
        self._append(
            self.setups_path,
            {
                "timestamp": timestamp,
                "symbol": recommendation["symbol"],
                "accepted": not blocked,
            },
        )
        if blocked:
            payload = {
                "timestamp": timestamp,
                "symbol": recommendation["symbol"],
                "market_regime": recommendation["market_regime"],
                "context_score": recommendation["context_score"],
                "entry_score": recommendation["entry_score"],
                "block_reason": self._block_reason(recommendation),
                "no_chase_blocked": bool(
                    recommendation.get("no_chase_blocked")
                ),
            }
            payload.update(
                {
                    field: recommendation[field]
                    for field in OPTIONAL_BLOCKED_SETUP_FIELDS
                    if field in recommendation
                }
            )
            self._append(
                self.blocked_setups_path,
                payload,
            )

    def record_post_cost_block(self, payload: dict[str, Any]) -> None:
        """Record a runner-level block after effective-entry cost normalization."""
        if payload.get("block_reason") != "invalid_post_cost_trade_geometry":
            raise ValueError("post-cost block must use invalid_post_cost_trade_geometry")
        self._append(self.post_cost_blocks_path, payload)

    def write_daily_summary(self, trading_date: str | None = None) -> dict[str, Any]:
        trading_date = trading_date or datetime.now(timezone.utc).date().isoformat()
        setups = [
            setup
            for setup in self._read(self.setups_path)
            if str(setup["timestamp"]).startswith(trading_date)
        ]
        trades = [
            trade
            for trade in self._read(self.trades_path)
            if str(trade["timestamp_close"]).startswith(trading_date)
        ]
        metrics = calculate_performance_metrics(trades)
        accepted = sum(bool(setup["accepted"]) for setup in setups)
        summary = {
            "date": trading_date,
            "total_setups": len(setups),
            "accepted_setups": accepted,
            "blocked_setups": len(setups) - accepted,
            "executed_trades": metrics["total_trades"],
            "wins": metrics["wins"],
            "losses": metrics["losses"],
            "win_rate": metrics["win_rate"],
            "expectancy": metrics["expectancy"],
            "profit_factor": metrics["profit_factor"],
        }
        self.summary_path.write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        return summary

    @staticmethod
    def _block_reason(recommendation: dict[str, Any]) -> str:
        if recommendation.get("blocked_by_quality_guard"):
            return str(recommendation.get("quality_block_reason"))
        if recommendation.get("no_chase_blocked"):
            return "no_chase"
        if recommendation.get("blocked_by_context"):
            return "context_score_below_threshold"
        return "entry_score_below_threshold"

    @staticmethod
    def _append(path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, separators=(",", ":")) + "\n")

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
