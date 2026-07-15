from pathlib import Path
from typing import Any

import pandas as pd

from trading_bot.journal.paper_forward import PaperForwardJournal
from trading_bot.analysis.edge_v2 import EdgeV2Diagnostics
from trading_bot.backtest.price_units import PriceUnitContract
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
    unit_columns = {"spread_points", "spread_price", "point_size", "tick_size"}
    if "spread" in data.columns and "spread_points" not in data.columns:
        raise ValueError("ambiguous legacy spread column; export spread_points and spread_price explicitly")
    present_units = unit_columns.intersection(data.columns)
    if present_units and present_units != unit_columns:
        missing_units = sorted(unit_columns.difference(data.columns))
        raise ValueError(f"incomplete price-unit contract in CSV: {', '.join(missing_units)}")
    numeric.extend(sorted(present_units))
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
        edge_v2_diagnostics: Any | None = None,
        price_units: PriceUnitContract | None = None,
        slippage_points: float = 0.0,
        slippage_price: float | None = None,
        warmup_bars: int = 21,
    ):
        if slippage_points < 0 or (slippage_price is not None and slippage_price < 0):
            raise ValueError("slippage must be non-negative")
        if slippage_price is not None and slippage_points:
            raise ValueError("declare slippage in either broker points or price units, not both")
        self.symbol = symbol
        self.timeframe = timeframe
        self.journal = journal
        self.signal_detector = signal_detector or LiquiditySweepDetector()
        self.context_engine = context_engine or ContextEngine()
        self.entry_scorer = entry_scorer or EntryScorer()
        self.edge_v2_diagnostics = edge_v2_diagnostics or EdgeV2Diagnostics()
        self.price_units = price_units
        self.slippage_points = slippage_points
        self._explicit_slippage_price = slippage_price
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
                "spread": self._spread_points(bar),
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
            edge_v2 = self.edge_v2_diagnostics.evaluate(history)
            recommendation = {
                "generated_at": bar["time"].isoformat(),
                "symbol": self.symbol,
                "setup": signal_report["setup"],
                **context,
                **entry_quality,
                **market_state,
                "atr": atr,
                "candle_range": candle_range,
                **edge_v2,
            }
            self.journal.record_setup(recommendation)
            if self._is_blocked(entry_quality):
                continue
            pending = {
                "setup": signal_report["setup"],
                "context": context,
                "entry_quality": entry_quality,
                "edge_v2": edge_v2,
                "market_state": market_state,
                "atr": atr,
                "candle_range": candle_range,
                "sweep_level": self._sweep_level(signal_report),
                "setup_close": float(bar["close"]),
                "setup_timestamp": bar["time"].isoformat(),
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
        costs = self._transaction_costs(bar)
        entry = float(bar["open"]) + costs["spread_price"] + costs["slippage_price"] if direction == "LONG" else float(
            bar["open"]
        ) - costs["spread_price"] - costs["slippage_price"]
        stop = float(setup["stop_loss"])
        target = float(setup["take_profit"])
        geometry_valid = stop < entry < target if direction == "LONG" else target < entry < stop
        if not geometry_valid:
            self.journal.record_post_cost_block(
                {
                    "timestamp": bar["time"].isoformat(),
                    "symbol": self.symbol,
                    "timeframe": self.timeframe,
                    "direction": direction,
                    "block_reason": "invalid_post_cost_trade_geometry",
                    "setup_timestamp": pending["setup_timestamp"],
                    "setup_close": pending["setup_close"],
                    "next_bar_open": float(bar["open"]),
                    "effective_entry": entry,
                    "stop_loss": stop,
                    "take_profit": target,
                    **costs,
                }
            )
            return None
        return {
            **pending,
            "direction": direction,
            "entry": entry,
            "timestamp_open": bar["time"].isoformat(),
            "open_index": bar_index,
            "spread": costs["spread_points"],
            **costs,
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
        if exit_reason == "take_profit" and pnl <= 0:
            raise ValueError("take-profit exit must produce positive PnL after geometry validation")
        if exit_reason == "stop_loss" and pnl >= 0:
            raise ValueError("stop-loss exit must produce negative PnL after geometry validation")
        context = trade["context"]
        return {
            "trade_id": self._trade_id(trade),
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
            "spread_points": trade["spread_points"],
            "point_size": trade["point_size"],
            "tick_size": trade["tick_size"],
            "spread_price": trade["spread_price"],
            "slippage_points": trade["slippage_points"],
            "slippage_price": trade["slippage_price"],
            "volatility": trade["market_state"]["volatility"],
            "atr": trade["atr"],
            "candle_range": trade["candle_range"],
            "risk_points": risk,
            "reward_points": reward,
            "planned_rr": reward / risk if risk else 0.0,
            "entry_distance_from_sweep": trade["entry_distance_from_sweep"],
            "bars_held": bar_index - trade["open_index"] + 1,
            "exit_reason": exit_reason,
            **trade["edge_v2"],
        }

    def _transaction_costs(self, bar: pd.Series) -> dict[str, float]:
        spread_points = self._spread_points(bar)
        point_size = bar.get("point_size")
        spread_price = bar.get("spread_price")
        tick_size = bar.get("tick_size")
        if spread_points > 0 and (point_size is None or pd.isna(point_size)):
            raise ValueError("positive spread_points requires authoritative point_size metadata")
        if point_size is None or pd.isna(point_size):
            if self.price_units is None:
                point_size_value = 0.0
                tick_size_value = 0.0
            else:
                point_size_value = self.price_units.point_size
                tick_size_value = self.price_units.tick_size
        else:
            point_size_value = float(point_size)
            tick_size_value = float(tick_size) if tick_size is not None and not pd.isna(tick_size) else point_size_value
        contract = self.price_units or (PriceUnitContract(point_size_value, tick_size_value) if point_size_value else None)
        if spread_price is None or pd.isna(spread_price):
            if spread_points:
                raise ValueError("positive spread_points requires spread_price metadata")
            spread_price_value = 0.0
        else:
            spread_price_value = float(spread_price)
        if contract is not None and not pd.isna(spread_price) and abs(contract.spread_price(spread_points) - spread_price_value) > 1e-12:
            raise ValueError("spread_price does not match spread_points multiplied by point_size")
        if self._explicit_slippage_price is not None:
            slippage_price_value = float(self._explicit_slippage_price)
        elif self.slippage_points:
            if contract is None:
                raise ValueError("slippage_points requires authoritative point_size metadata")
            slippage_price_value = contract.slippage_price(self.slippage_points)
        else:
            slippage_price_value = 0.0
        return {
            "spread_points": spread_points,
            "point_size": point_size_value,
            "tick_size": tick_size_value,
            "spread_price": spread_price_value,
            "slippage_points": float(self.slippage_points),
            "slippage_price": slippage_price_value,
        }

    @staticmethod
    def _spread_points(bar: pd.Series) -> float:
        spread = bar.get("spread_points", 0.0)
        return 0.0 if pd.isna(spread) else float(spread)

    def _trade_id(self, trade: dict[str, Any]) -> str:
        return "-".join(
            (self.symbol, self.timeframe, str(trade["timestamp_open"]), str(trade["direction"]), str(trade["open_index"]))
        )

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
