from pathlib import Path
from typing import Any

import pandas as pd

from trading_bot.journal.paper_forward import PaperForwardJournal
from trading_bot.metrics.performance import calculate_performance_metrics
from trading_bot.signals.aqtf import ContextEngine, EntryScorer
from trading_bot.signals.liquidity_sweep import LiquiditySweepDetector


CSV_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


def load_historical_csv(path: str | Path) -> pd.DataFrame:
    """Load and normalize chronological OHLCV candles."""
    data = pd.read_csv(path)
    missing = CSV_COLUMNS.difference(data.columns)
    if missing:
        raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")
    data = data.rename(columns={"timestamp": "time", "volume": "tick_volume"})
    if data.empty:
        return data
    data["time"] = pd.to_datetime(data["time"], utc=True, errors="raise")
    numeric = ["open", "high", "low", "close", "tick_volume"]
    if "spread" in data.columns:
        numeric.append("spread")
    data[numeric] = data[numeric].apply(pd.to_numeric, errors="raise")
    return data.sort_values("time").reset_index(drop=True)


class BacktestRunner:
    """Replay candles without exposing future data to strategy components."""

    def __init__(
        self,
        *,
        symbol: str,
        timeframe: str,
        journal: PaperForwardJournal,
        signal_detector: Any | None = None,
        context_engine: Any | None = None,
        entry_scorer: Any | None = None,
        default_spread: float = 0.0,
        slippage_points: float = 0.0,
        warmup_bars: int = 21,
    ):
        if default_spread < 0 or slippage_points < 0:
            raise ValueError("spread and slippage must be non-negative")
        self.symbol = symbol
        self.timeframe = timeframe
        self.journal = journal
        self.signal_detector = signal_detector or LiquiditySweepDetector()
        self.context_engine = context_engine or ContextEngine()
        self.entry_scorer = entry_scorer or EntryScorer()
        self.default_spread = default_spread
        self.slippage_points = slippage_points
        self.warmup_bars = warmup_bars

    def run(self, data: pd.DataFrame) -> dict[str, int | float | None]:
        if data.empty:
            self.journal.write_daily_summary()
            return calculate_performance_metrics([])

        completed: list[dict[str, Any]] = []
        pending: dict[str, Any] | None = None
        open_trade: dict[str, Any] | None = None

        for index in range(len(data)):
            bar = data.iloc[index]

            if pending is not None:
                open_trade = self._open_trade(pending, bar, index)
                pending = None

            if open_trade is not None:
                exit_result = self._exit_price(open_trade, bar)
                if exit_result is not None:
                    exit_price, exit_reason = exit_result
                    record = self._close_trade(
                        open_trade,
                        bar,
                        exit_price,
                        index,
                        exit_reason,
                    )
                    self.journal.record_completed_trade(record)
                    completed.append(record)
                    open_trade = None
                else:
                    continue

            if index + 1 < self.warmup_bars or index + 1 >= len(data):
                continue

            history = data.iloc[: index + 1].copy()
            signal_report = self.signal_detector.detect_signals(history)
            if not signal_report.get("setup"):
                continue

            h1_data = self._completed_h1(history, bar["time"])
            context = self.context_engine.evaluate(h1_data)
            market_state = {
                "spread": self._spread(bar),
                "volatility": self._volatility(history),
            }
            atr = self._atr(history)
            candle_range = float(bar["high"]) - float(bar["low"])
            entry_quality = self.entry_scorer.evaluate(
                signal_report,
                history,
                context,
                market_state,
            )
            recommendation = {
                "generated_at": bar["time"].isoformat(),
                "symbol": self.symbol,
                "setup": signal_report["setup"],
                **context,
                **entry_quality,
                **market_state,
                "atr": atr,
                "candle_range": candle_range,
            }
            self.journal.record_setup(recommendation)
            if self._is_blocked(entry_quality):
                continue
            pending = {
                "setup": signal_report["setup"],
                "context": context,
                "entry_quality": entry_quality,
                "market_state": market_state,
                "atr": atr,
                "candle_range": candle_range,
                "sweep_level": self._sweep_level(signal_report),
            }

        if open_trade is not None:
            final_bar = data.iloc[-1]
            record = self._close_trade(
                open_trade,
                final_bar,
                float(final_bar["close"]),
                len(data) - 1,
                "end_of_data",
            )
            self.journal.record_completed_trade(record)
            completed.append(record)

        trading_date = data.iloc[-1]["time"].date().isoformat()
        self.journal.write_daily_summary(trading_date)
        return calculate_performance_metrics(completed)

    def _open_trade(
        self,
        pending: dict[str, Any],
        bar: pd.Series,
        bar_index: int,
    ) -> dict[str, Any]:
        setup = pending["setup"]
        direction = str(setup["type"])
        cost = self._spread(bar) + self.slippage_points
        entry = float(bar["open"]) + cost if direction == "LONG" else float(
            bar["open"]
        ) - cost
        return {
            **pending,
            "direction": direction,
            "entry": entry,
            "timestamp_open": bar["time"].isoformat(),
            "open_index": bar_index,
            "spread": self._spread(bar),
            "entry_distance_from_sweep": (
                abs(entry - float(pending["sweep_level"]))
                if pending["sweep_level"] is not None
                else None
            ),
        }

    @staticmethod
    def _exit_price(
        trade: dict[str, Any],
        bar: pd.Series,
    ) -> tuple[float, str] | None:
        setup = trade["setup"]
        stop = float(setup["stop_loss"])
        target = float(setup["take_profit"])
        if trade["direction"] == "LONG":
            if float(bar["low"]) <= stop:
                return stop, "stop_loss"
            if float(bar["high"]) >= target:
                return target, "take_profit"
        else:
            if float(bar["high"]) >= stop:
                return stop, "stop_loss"
            if float(bar["low"]) <= target:
                return target, "take_profit"
        return None

    def _close_trade(
        self,
        trade: dict[str, Any],
        bar: pd.Series,
        exit_price: float,
        bar_index: int,
        exit_reason: str,
    ) -> dict[str, Any]:
        setup = trade["setup"]
        multiplier = 1.0 if trade["direction"] == "LONG" else -1.0
        pnl = (exit_price - trade["entry"]) * multiplier
        risk = abs(trade["entry"] - float(setup["stop_loss"]))
        reward = abs(float(setup["take_profit"]) - trade["entry"])
        outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "breakeven"
        context = trade["context"]
        return {
            "trade_id": f"{self.symbol}-{trade['timestamp_open']}",
            "timestamp_open": trade["timestamp_open"],
            "timestamp_close": bar["time"].isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": trade["direction"],
            "entry": trade["entry"],
            "stop_loss": float(setup["stop_loss"]),
            "take_profit": float(setup["take_profit"]),
            "exit_price": exit_price,
            "pnl": pnl,
            "r_multiple": pnl / risk if risk else 0.0,
            "outcome": outcome,
            "market_regime": context["market_regime"],
            "context_bias": context["context_bias"],
            "context_score": context["context_score"],
            "context_reason": context["context_reason"],
            "entry_score": trade["entry_quality"]["entry_score"],
            "distance_to_h1_high": context["distance_to_h1_high"],
            "distance_to_h1_low": context["distance_to_h1_low"],
            "distance_to_h1_mid": context["distance_to_h1_mid"],
            "extension_atr": trade["entry_quality"].get("extension_atr"),
            "spread": trade["spread"],
            "volatility": trade["market_state"]["volatility"],
            "atr": trade["atr"],
            "candle_range": trade["candle_range"],
            "risk_points": risk,
            "reward_points": reward,
            "planned_rr": reward / risk if risk else 0.0,
            "entry_distance_from_sweep": trade["entry_distance_from_sweep"],
            "bars_held": bar_index - trade["open_index"] + 1,
            "exit_reason": exit_reason,
        }

    def _spread(self, bar: pd.Series) -> float:
        spread = bar.get("spread")
        return self.default_spread if pd.isna(spread) else float(spread)

    @staticmethod
    def _volatility(history: pd.DataFrame) -> float:
        returns = history["close"].astype(float).pct_change().dropna()
        if len(returns) < 2:
            return 0.0
        value = returns.std(ddof=1)
        return 0.0 if pd.isna(value) else float(value)

    @staticmethod
    def _atr(history: pd.DataFrame, period: int = 14) -> float:
        ranges = (
            history["high"].astype(float) - history["low"].astype(float)
        ).tail(period)
        return float(ranges.mean()) if not ranges.empty else 0.0

    @staticmethod
    def _sweep_level(signal_report: dict[str, Any]) -> float | None:
        liquidity = signal_report.get("liquidity") or {}
        setup = signal_report.get("setup") or {}
        key = "recent_low" if setup.get("type") == "LONG" else "recent_high"
        value = liquidity.get(key)
        return float(value) if value is not None else None

    @staticmethod
    def _completed_h1(history: pd.DataFrame, timestamp: Any) -> pd.DataFrame:
        indexed = history.set_index("time")
        h1 = indexed.resample("1h", label="right", closed="left").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "tick_volume": "sum",
            }
        )
        h1 = h1.dropna(subset=["open", "high", "low", "close"])
        return h1.loc[h1.index <= timestamp].reset_index()

    @staticmethod
    def _is_blocked(entry_quality: dict[str, Any]) -> bool:
        return bool(
            entry_quality["blocked_by_context"]
            or entry_quality["blocked_by_entry_score"]
            or entry_quality["no_chase_blocked"]
            or entry_quality.get("blocked_by_quality_guard", False)
        )
