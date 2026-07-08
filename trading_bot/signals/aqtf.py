from typing import Any

import pandas as pd


class ContextEngine:
    """Classify a small H1 price sample into a practical market context."""

    def __init__(self, moving_average_period: int = 10, minimum_bars: int = 8):
        self.moving_average_period = moving_average_period
        self.minimum_bars = minimum_bars

    def evaluate(self, data: pd.DataFrame) -> dict[str, Any]:
        required = {"high", "low", "close"}
        if len(data) < self.minimum_bars or not required.issubset(data.columns):
            return self._result("unknown", "neutral", 0, "insufficient H1 data")

        recent = data.tail(max(self.moving_average_period, self.minimum_bars))
        midpoint = len(recent) // 2
        earlier = recent.iloc[:midpoint]
        later = recent.iloc[midpoint:]
        close = float(recent["close"].iloc[-1])
        moving_average = float(recent["close"].mean())
        rising = (
            later["high"].mean() > earlier["high"].mean()
            and later["low"].mean() > earlier["low"].mean()
        )
        falling = (
            later["high"].mean() < earlier["high"].mean()
            and later["low"].mean() < earlier["low"].mean()
        )

        ranges = recent["high"].astype(float) - recent["low"].astype(float)
        prior_ranges = ranges.iloc[-6:-3]
        latest_ranges = ranges.iloc[-3:]
        if len(prior_ranges) == 3 and prior_ranges.mean() > 0:
            range_ratio = float(latest_ranges.mean() / prior_ranges.mean())
            if range_ratio < 0.7:
                return self._result(
                    "compression", "neutral", 50, "recent H1 ranges are shrinking"
                )
            if range_ratio > 1.5:
                bias = "long" if close >= moving_average else "short"
                return self._result(
                    "expansion", bias, 65, f"H1 ranges expanding with {bias} bias"
                )

        if close > moving_average and rising:
            return self._result(
                "trend_up", "long", 75, "H1 close above average with rising structure"
            )
        if close < moving_average and falling:
            return self._result(
                "trend_down",
                "short",
                75,
                "H1 close below average with falling structure",
            )

        overlap = float(recent["low"].max()) <= float(recent["high"].min())
        if overlap:
            return self._result(
                "range", "neutral", 55, "recent H1 highs and lows overlap"
            )
        return self._result("range", "neutral", 50, "H1 structure has no clear bias")

    @staticmethod
    def _result(
        regime: str,
        bias: str,
        score: int,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "market_regime": regime,
            "context_bias": bias,
            "context_score": score,
            "context_reason": reason,
        }


class EntryScorer:
    """Score an existing liquidity sweep without creating new signals."""

    def __init__(
        self,
        *,
        context_score_min: int = 60,
        entry_score_min: int = 65,
        no_chase_max_atr: float = 0.6,
        spread_limit: float = 20,
        volatility_limit: float = 0.005,
    ):
        self.context_score_min = context_score_min
        self.entry_score_min = entry_score_min
        self.no_chase_max_atr = no_chase_max_atr
        self.spread_limit = spread_limit
        self.volatility_limit = volatility_limit

    def evaluate(
        self,
        signal_report: dict[str, Any],
        m5_data: pd.DataFrame,
        context: dict[str, Any],
        market_state: dict[str, Any],
    ) -> dict[str, Any]:
        setup = signal_report.get("setup")
        if not setup:
            return {
                "entry_score": 0,
                "entry_reason": "no liquidity sweep setup",
                "blocked_by_context": context["context_score"]
                < self.context_score_min,
                "blocked_by_entry_score": True,
                "no_chase_blocked": False,
                "no_chase_reason": "no setup to evaluate",
                "extension_atr": None,
            }

        direction = str(setup["type"])
        expected_bias = "long" if direction == "LONG" else "short"
        score = 55
        reasons = ["liquidity sweep confirmed"]

        if context["context_bias"] == expected_bias:
            score += 20
            reasons.append("aligned with H1 context")
        elif context["context_bias"] not in {"neutral", expected_bias}:
            score -= 20
            reasons.append("opposes H1 context")

        liquidity = signal_report.get("liquidity", {})
        level = (
            liquidity.get("recent_low")
            if direction == "LONG"
            else liquidity.get("recent_high")
        )
        entry_price = float(setup["entry_price"])
        reclaimed = level is not None and (
            (direction == "LONG" and entry_price > float(level))
            or (direction == "SHORT" and entry_price < float(level))
        )
        if reclaimed:
            score += 10
            reasons.append("prior range reclaimed")

        extension_atr = self._extension_atr(
            direction=direction,
            entry_price=entry_price,
            sweep_level=level,
            data=m5_data,
        )
        no_chase_blocked = (
            extension_atr is not None and extension_atr > self.no_chase_max_atr
        )
        if no_chase_blocked:
            score -= 25
            reasons.append("entry exceeds no-chase limit")

        if self._is_degraded(market_state):
            score -= 15
            reasons.append("spread or volatility degraded")

        score = max(0, min(100, score))
        blocked_by_context = context["context_score"] < self.context_score_min
        blocked_by_entry_score = score < self.entry_score_min or no_chase_blocked
        return {
            "entry_score": score,
            "entry_reason": "; ".join(reasons),
            "blocked_by_context": blocked_by_context,
            "blocked_by_entry_score": blocked_by_entry_score,
            "no_chase_blocked": no_chase_blocked,
            "no_chase_reason": (
                f"extension {extension_atr:.2f} ATR exceeds "
                f"{self.no_chase_max_atr:.2f}"
                if no_chase_blocked
                else "entry remains within no-chase limit"
            ),
            "extension_atr": extension_atr,
        }

    def _extension_atr(
        self,
        *,
        direction: str,
        entry_price: float,
        sweep_level: Any,
        data: pd.DataFrame,
    ) -> float | None:
        if sweep_level is None or not {"high", "low"}.issubset(data.columns):
            return None
        ranges = data["high"].astype(float) - data["low"].astype(float)
        atr = float(ranges.tail(14).mean())
        if atr <= 0:
            return None
        extension = (
            entry_price - float(sweep_level)
            if direction == "LONG"
            else float(sweep_level) - entry_price
        )
        return max(0.0, extension / atr)

    def _is_degraded(self, market_state: dict[str, Any]) -> bool:
        spread = market_state.get("spread")
        volatility = market_state.get("volatility")
        return (
            spread is None
            or volatility is None
            or float(spread) > self.spread_limit
            or float(volatility) > self.volatility_limit
        )
