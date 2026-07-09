from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


class MT5HistoryError(RuntimeError):
    """Raised when local MT5 history cannot be exported."""


def resolve_timeframe(gateway: Any, timeframe: str) -> Any:
    mapping = {
        "M5": "TIMEFRAME_M5",
        "M15": "TIMEFRAME_M15",
        "H1": "TIMEFRAME_H1",
        "H4": "TIMEFRAME_H4",
    }
    normalized = timeframe.upper()
    if normalized not in mapping:
        raise MT5HistoryError(f"Unsupported timeframe: {timeframe}")
    return getattr(gateway, mapping[normalized])


def export_mt5_history(
    gateway: Any,
    *,
    symbol: str,
    timeframe: str,
    bars: int,
    output: str | Path,
) -> Path:
    if bars <= 0:
        raise MT5HistoryError("bars must be greater than zero")
    if gateway.symbol_info(symbol) is None:
        raise MT5HistoryError(f"MT5 symbol is unavailable: {symbol}")

    rates = gateway.copy_rates_from_pos(
        symbol,
        resolve_timeframe(gateway, timeframe),
        0,
        bars,
    )
    if rates is None or len(rates) == 0:
        raise MT5HistoryError(
            f"No MT5 history returned for {symbol} {timeframe}"
        )

    return _write_export(rates, output)


def export_mt5_history_range(
    gateway: Any,
    *,
    symbol: str,
    timeframe: str,
    start: str | datetime,
    end: str | datetime,
    output: str | Path,
) -> Path:
    if gateway.symbol_info(symbol) is None:
        raise MT5HistoryError(f"MT5 symbol is unavailable: {symbol}")
    start_time = _parse_utc(start)
    end_time = _parse_utc(end)
    if end_time <= start_time:
        raise MT5HistoryError("MT5 history end must be after start")
    rates = gateway.copy_rates_range(
        symbol,
        resolve_timeframe(gateway, timeframe),
        start_time,
        end_time,
    )
    if rates is None or len(rates) == 0:
        raise MT5HistoryError(
            f"No MT5 history returned for {symbol} {timeframe} in requested range"
        )
    return _write_export(rates, output)


def _write_export(rates: Any, output: str | Path) -> Path:
    source = pd.DataFrame(rates)
    required = {"time", "open", "high", "low", "close", "tick_volume"}
    missing = required.difference(source.columns)
    if missing:
        raise MT5HistoryError(
            f"MT5 history missing fields: {', '.join(sorted(missing))}"
        )

    tick_volume = source["tick_volume"].fillna(0)
    if "real_volume" in source:
        real_volume = source["real_volume"].fillna(0)
        volume = real_volume.where(real_volume > 0, tick_volume)
    else:
        volume = tick_volume
    spread = source["spread"].fillna(0) if "spread" in source else 0

    exported = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(source["time"], unit="s", utc=True),
            "open": source["open"],
            "high": source["high"],
            "low": source["low"],
            "close": source["close"],
            "volume": volume,
            "spread": spread,
        }
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    exported.to_csv(output_path, index=False)
    return output_path


def _parse_utc(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def export_from_local_terminal(
    *,
    symbol: str,
    timeframe: str,
    bars: int,
    output: str | Path,
    gateway: Any | None = None,
) -> Path:
    if gateway is None:
        try:
            import MetaTrader5 as gateway
        except ImportError as exc:
            raise MT5HistoryError("MetaTrader5 package is unavailable") from exc

    if not gateway.initialize():
        raise MT5HistoryError(
            f"MT5 terminal is unavailable: {gateway.last_error()}"
        )
    try:
        return export_mt5_history(
            gateway,
            symbol=symbol,
            timeframe=timeframe,
            bars=bars,
            output=output,
        )
    finally:
        gateway.shutdown()


def export_range_from_local_terminal(
    *,
    symbol: str,
    timeframe: str,
    start: str | datetime,
    end: str | datetime,
    output: str | Path,
    gateway: Any | None = None,
) -> Path:
    if gateway is None:
        try:
            import MetaTrader5 as gateway
        except ImportError as exc:
            raise MT5HistoryError("MetaTrader5 package is unavailable") from exc

    if not gateway.initialize():
        raise MT5HistoryError(
            f"MT5 terminal is unavailable: {gateway.last_error()}"
        )
    try:
        return export_mt5_history_range(
            gateway,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            output=output,
        )
    finally:
        gateway.shutdown()
