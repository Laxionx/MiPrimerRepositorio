from __future__ import annotations

import math
from typing import Any

import pandas as pd


EDGE_V2_FIELDS = (
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


class EdgeV2Diagnostics:
    """Describe compression and range pressure without affecting trade decisions."""

    def __init__(self, *, window_bars: int = 5):
        if window_bars < 2:
            raise ValueError("window_bars must be at least two")
        self.window_bars = window_bars

    def evaluate(self, data: pd.DataFrame) -> dict[str, Any]:
        required = {"high", "low", "close"}
        required_bars = self.window_bars * 2
        if len(data) < required_bars or not required.issubset(data.columns):
            return self._unknown()

        sample = data.tail(required_bars)
        numeric = sample[["high", "low", "close"]].apply(
            pd.to_numeric,
            errors="coerce",
        )
        if numeric.isna().any().any():
            return self._unknown()

        prior = numeric.iloc[: self.window_bars]
        recent = numeric.iloc[self.window_bars :]
        prior_ranges = prior["high"] - prior["low"]
        recent_ranges = recent["high"] - recent["low"]
        prior_average = float(prior_ranges.mean())
        recent_average = float(recent_ranges.mean())
        contraction_pct = self._contraction_pct(prior_average, recent_average)
        compression_score = (
            self._score(contraction_pct) if contraction_pct is not None else 0
        )

        range_high = float(recent["high"].max())
        range_low = float(recent["low"].min())
        range_points = range_high - range_low
        closes = [float(value) for value in recent["close"]]
        pressure = self._pressure(closes, range_low, range_high)

        duration = 0
        if prior_average > 0:
            for candle_range in reversed([float(value) for value in recent_ranges]):
                if candle_range > prior_average:
                    break
                duration += 1

        return {
            "compression_score": compression_score,
            "is_compressing": compression_score >= 60,
            "range_duration_bars": duration,
            "atr_contraction_pct": contraction_pct,
            "recent_range_points": range_points,
            "prior_range_points": float(prior["high"].max() - prior["low"].min()),
            **pressure,
        }

    @staticmethod
    def _contraction_pct(prior_average: float, recent_average: float) -> float | None:
        if prior_average <= 0:
            return None
        return round(max(0.0, (prior_average - recent_average) / prior_average * 100), 4)

    @staticmethod
    def _score(contraction_pct: float) -> int:
        return max(0, min(100, round(contraction_pct)))

    def _pressure(
        self,
        closes: list[float],
        range_low: float,
        range_high: float,
    ) -> dict[str, Any]:
        range_points = range_high - range_low
        if range_points <= 0:
            return {
                "pressure_score": 0,
                "pressure_direction": "neutral",
                "price_position_in_range": None,
                "upper_quartile_closes": 0,
                "lower_quartile_closes": 0,
                "average_pullback_depth": None,
            }

        upper_threshold = range_low + range_points * 0.75
        lower_threshold = range_low + range_points * 0.25
        upper_count = sum(close >= upper_threshold for close in closes)
        lower_count = sum(close <= lower_threshold for close in closes)
        minimum_cluster = math.ceil(self.window_bars * 0.6)
        if upper_count >= minimum_cluster and upper_count > lower_count:
            direction = "long"
        elif lower_count >= minimum_cluster and lower_count > upper_count:
            direction = "short"
        else:
            direction = "neutral"

        long_pullback = self._average_pullback(closes, range_points, "long")
        short_pullback = self._average_pullback(closes, range_points, "short")
        if direction == "long":
            pullback = long_pullback
            cluster = upper_count
        elif direction == "short":
            pullback = short_pullback
            cluster = lower_count
        else:
            pullback = round((long_pullback + short_pullback) / 2, 4)
            cluster = 0

        score = 0
        if direction != "neutral":
            score = self._score(
                cluster / self.window_bars * 70 + (1.0 - pullback) * 30
            )
        return {
            "pressure_score": score,
            "pressure_direction": direction,
            "price_position_in_range": max(
                0.0,
                min(1.0, (closes[-1] - range_low) / range_points),
            ),
            "upper_quartile_closes": upper_count,
            "lower_quartile_closes": lower_count,
            "average_pullback_depth": pullback,
        }

    @staticmethod
    def _average_pullback(
        closes: list[float],
        range_points: float,
        direction: str,
    ) -> float:
        anchor = closes[0]
        depths = []
        for close in closes[1:]:
            depth = (anchor - close) if direction == "long" else (close - anchor)
            depths.append(max(0.0, depth) / range_points)
            anchor = max(anchor, close) if direction == "long" else min(anchor, close)
        return round(sum(depths) / len(depths), 4) if depths else 0.0

    @staticmethod
    def _unknown() -> dict[str, None]:
        return {field: None for field in EDGE_V2_FIELDS}
