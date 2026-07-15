"""Explicit broker-point to price-unit conversion for research backtests."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class PriceUnitContract:
    """Authoritative instrument metadata used to normalize broker-point costs."""

    point_size: float
    tick_size: float

    def __post_init__(self) -> None:
        for name, value in (("point_size", self.point_size), ("tick_size", self.tick_size)):
            if not isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{name} must be a positive finite price increment")

    def spread_price(self, spread_points: float) -> float:
        return self._price_from_points(spread_points, "spread_points")

    def slippage_price(self, slippage_points: float) -> float:
        return self._price_from_points(slippage_points, "slippage_points")

    def _price_from_points(self, points: float, field: str) -> float:
        numeric = float(points)
        if not isfinite(numeric) or numeric < 0:
            raise ValueError(f"{field} must be a non-negative finite broker-point value")
        return numeric * float(self.point_size)
