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
            return self._result(
                "unknown",
                "neutral",
                0,
                "Insufficient H1 data",
                self._unknown_distances(),
            )

        recent = data.tail(max(self.moving_average_period, self.minimum_bars))
        midpoint = len(recent) // 2
        earlier = recent.iloc[:midpoint]
        later = recent.iloc[midpoint:]
        close = float(recent["close"].iloc[-1])
        moving_average = float(recent["close"].mean())
        distances = self._location(recent, close)
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
                    "compression",
                    "neutral",
                    self._context_score("compression", "neutral", distances),
                    self._location_reason("Compression", distances),
                    distances,
                )

        if close > moving_average and rising:
            return self._result(
                "trend",
                "long",
                self._context_score("trend", "long", distances),
                self._trend_reason("long", distances),
                distances,
            )
        if close < moving_average and falling:
            return self._result(
                "trend",
                "short",
                self._context_score("trend", "short", distances),
                self._trend_reason("short", distances),
                distances,
            )

        return self._result(
            "range",
            "neutral",
            self._context_score("range", "neutral", distances),
            self._location_reason("Range", distances),
            distances,
        )

    @staticmethod
    def _result(
        regime: str,
        bias: str,
        score: int,
        reason: str,
        distances: dict[str, float | None],
    ) -> dict[str, Any]:
        return {
            "market_regime": regime,
            "context_bias": bias,
            "context_score": score,
            "context_reason": reason,
            **distances,
        }

    @staticmethod
    def _location(data: pd.DataFrame, close: float) -> dict[str, float]:
        h1_high = float(data["high"].max())
        h1_low = float(data["low"].min())
        h1_range = h1_high - h1_low
        if h1_range <= 0:
            return {
                "distance_to_h1_high": 0.0,
                "distance_to_h1_low": 0.0,
                "distance_to_h1_mid": 0.0,
            }
        h1_mid = (h1_high + h1_low) / 2
        return {
            "distance_to_h1_high": max(0.0, (h1_high - close) / h1_range),
            "distance_to_h1_low": max(0.0, (close - h1_low) / h1_range),
            "distance_to_h1_mid": abs(close - h1_mid) / h1_range,
        }

    @staticmethod
    def _unknown_distances() -> dict[str, None]:
        return {
            "distance_to_h1_high": None,
            "distance_to_h1_low": None,
            "distance_to_h1_mid": None,
        }

    @staticmethod
    def _location_reason(
        prefix: str,
        distances: dict[str, float | None],
    ) -> str:
        if distances["distance_to_h1_high"] <= 0.2:
            return f"{prefix} near H1 high"
        if distances["distance_to_h1_low"] <= 0.2:
            return f"{prefix} near H1 low"
        if prefix == "Range":
            return "Range center"
        return "Compression near H1 mid"

    @staticmethod
    def _trend_reason(
        bias: str,
        distances: dict[str, float | None],
    ) -> str:
        continuation = (
            bias == "long" and distances["distance_to_h1_high"] <= 0.25
        ) or (bias == "short" and distances["distance_to_h1_low"] <= 0.25)
        return "Trend continuation" if continuation else "Trend pullback"

    @staticmethod
    def _context_score(
        regime: str,
        bias: str,
        distances: dict[str, float | None],
    ) -> int:
        if regime == "trend":
            directional_distance = (
                distances["distance_to_h1_high"]
                if bias == "long"
                else distances["distance_to_h1_low"]
            )
            location_quality = 1.0 - min(max(float(directional_distance), 0.0), 1.0)
            return 65 + round(location_quality * 15)
        if regime == "range":
            edge_distance = min(
                float(distances["distance_to_h1_high"]),
                float(distances["distance_to_h1_low"]),
            )
            return 45 + round((1.0 - min(edge_distance * 2, 1.0)) * 10)
        distance_from_mid = min(
            float(distances["distance_to_h1_mid"]) * 2,
            1.0,
        )
        return 40 + round(distance_from_mid * 15)


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
        score = 40
        reasons = ["liquidity sweep confirmed"]

        if context["context_bias"] == expected_bias:
            score += 15
            reasons.append("aligned with H1 context")
        elif context["context_bias"] not in {"neutral", expected_bias}:
            score -= 15
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
            score += 8
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
        elif extension_atr is not None:
            score += self._extension_quality(extension_atr)
            reasons.append("extension quality measured")

        score += self._sweep_quality(direction, level, m5_data)
        spread_points = self._quality_points(
            market_state.get("spread"),
            self.spread_limit,
        )
        volatility_points = self._quality_points(
            market_state.get("volatility"),
            self.volatility_limit,
        )
        score += spread_points + volatility_points
        reasons.append("spread and volatility quality measured")

        score = max(0, min(89, score))
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

    @staticmethod
    def _extension_quality(extension_atr: float) -> int:
        distance_from_balanced_reclaim = abs(extension_atr - 0.25)
        return max(0, 10 - round(distance_from_balanced_reclaim * 20))

    @staticmethod
    def _quality_points(value: Any, limit: float) -> int:
        if value is None or limit <= 0:
            return 0
        ratio = min(max(float(value) / limit, 0.0), 1.0)
        return round((1.0 - ratio) * 10)

    @staticmethod
    def _sweep_quality(
        direction: str,
        level: Any,
        data: pd.DataFrame,
    ) -> int:
        if level is None or data.empty or not {"high", "low"}.issubset(data.columns):
            return 0
        ranges = data["high"].astype(float) - data["low"].astype(float)
        atr = float(ranges.tail(14).mean())
        if atr <= 0:
            return 0
        current = data.iloc[-1]
        penetration = (
            float(level) - float(current["low"])
            if direction == "LONG"
            else float(current["high"]) - float(level)
        )
        normalized = min(max(penetration / atr, 0.0), 1.0)
        return round(normalized * 8)
