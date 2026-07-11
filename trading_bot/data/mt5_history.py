from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from math import isfinite

import pandas as pd


class MT5HistoryError(RuntimeError):
    """Raised when local MT5 history cannot be exported."""


PAGINATED_REQUIRED_COLUMNS = {
    "time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume",
}
TIMEFRAME_SECONDS = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400}


@dataclass(frozen=True)
class PaginatedHistoryExport:
    csv_path: Path
    manifest_path: Path
    manifest: dict[str, Any]


@dataclass(frozen=True)
class InstrumentPriceMetadata:
    point_size: float
    tick_size: float

    def as_manifest(self) -> dict[str, Any]:
        return {
            "spread_points_source": "MT5 rates.spread",
            "point_size": self.point_size,
            "tick_size": self.tick_size,
            "spread_price_formula": "spread_points * point_size",
            "slippage_points_unit": "broker_points",
        }


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
    metadata = instrument_price_metadata(gateway, symbol)

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

    return _write_export(rates, output, metadata)


def export_mt5_history_range(
    gateway: Any,
    *,
    symbol: str,
    timeframe: str,
    start: str | datetime,
    end: str | datetime,
    output: str | Path,
    manifest_out: str | Path | None = None,
) -> Path:
    metadata = instrument_price_metadata(gateway, symbol)
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
    csv_path = _write_export(rates, output, metadata)
    if manifest_out is not None:
        _write_range_manifest(
            manifest_out=Path(manifest_out),
            symbol=symbol,
            timeframe=timeframe,
            start=start_time,
            end=end_time,
            csv_path=csv_path,
            metadata=metadata,
        )
    return csv_path


def export_mt5_history_paginated(
    gateway: Any,
    *,
    symbol: str,
    timeframe: str,
    start: str | datetime,
    end: str | datetime,
    output: str | Path,
    manifest_out: str | Path,
    page_size: int = 5_000,
    include_current_bar: bool = False,
    require_complete: bool = True,
) -> PaginatedHistoryExport:
    """Export a UTC-normalized MT5 range through read-only position pages."""
    start_time = _parse_utc(start)
    end_time = _parse_utc(end)
    manifest_path = Path(manifest_out)
    manifest = _pagination_manifest(
        symbol=symbol,
        timeframe=timeframe,
        start=start_time,
        end=end_time,
        page_size=page_size,
        include_current_bar=include_current_bar,
        require_complete=require_complete,
    )
    if page_size <= 0:
        _fail_paginated(manifest, manifest_path, "integrity_failed", "page_size must be greater than zero")
    if end_time < start_time:
        _fail_paginated(manifest, manifest_path, "integrity_failed", "MT5 history end must not be before start")
    try:
        metadata = instrument_price_metadata(gateway, symbol)
    except MT5HistoryError as exc:
        _fail_paginated(manifest, manifest_path, "environment_blocked", str(exc))
    manifest["price_unit_contract"] = metadata.as_manifest()

    resolved_timeframe = resolve_timeframe(gateway, timeframe)
    position = 0 if include_current_bar else 1
    maxbars = _terminal_maxbars(gateway)
    pages: list[pd.DataFrame] = []
    reached_start = False

    while True:
        requested_count = page_size if maxbars is None else min(page_size, maxbars - position)
        if requested_count <= 0:
            break
        rates = gateway.copy_rates_from_pos(symbol, resolved_timeframe, position, requested_count)
        last_error = _last_error(gateway)
        page = _page_manifest(position, requested_count, rates, last_error)
        manifest["pages"].append(page)
        if rates is None:
            _fail_paginated(manifest, manifest_path, "environment_blocked", "MT5 page request failed")
        frame = pd.DataFrame(rates)
        if frame.empty:
            break
        missing = PAGINATED_REQUIRED_COLUMNS.difference(frame.columns)
        if missing:
            _fail_paginated(
                manifest,
                manifest_path,
                "integrity_failed",
                f"MT5 paginated history missing fields: {', '.join(sorted(missing))}",
            )
        timestamps = pd.to_datetime(frame["time"], unit="s", utc=True, errors="coerce")
        if timestamps.isna().any():
            _fail_paginated(manifest, manifest_path, "integrity_failed", "MT5 paginated history has invalid timestamps")
        page["page_start"] = timestamps.min().isoformat()
        page["page_end"] = timestamps.max().isoformat()
        pages.append(frame)
        if timestamps.min().to_pydatetime() <= start_time:
            reached_start = True
            break
        if len(frame) < requested_count:
            break
        position += requested_count

    if not pages:
        _fail_paginated(manifest, manifest_path, "partial_history_boundary", "MT5 history ended before requested range")
    if not reached_start and require_complete:
        _fail_paginated(manifest, manifest_path, "partial_history_boundary", "MT5 history is partial before requested start")

    source = pd.concat(pages, ignore_index=True)
    manifest["raw_bars"] = len(source)
    source["_timestamp"] = pd.to_datetime(source["time"], unit="s", utc=True, errors="raise")
    source = source.sort_values("_timestamp", kind="stable").reset_index(drop=True)
    duplicate_count = 0
    for _, duplicate_rows in source[source.duplicated("_timestamp", keep=False)].groupby("_timestamp", sort=False):
        if any(duplicate_rows[column].nunique(dropna=False) > 1 for column in PAGINATED_REQUIRED_COLUMNS):
            _fail_paginated(manifest, manifest_path, "integrity_failed", "conflicting duplicate timestamp in MT5 history")
        duplicate_count += len(duplicate_rows) - 1
    source = source.drop_duplicates("_timestamp", keep="first")
    manifest["duplicate_bars"] = duplicate_count
    manifest["conflicting_duplicates"] = 0
    manifest["unique_bars"] = len(source)
    filtered = source[(source["_timestamp"] >= start_time) & (source["_timestamp"] <= end_time)].copy()
    if filtered.empty:
        _fail_paginated(manifest, manifest_path, "partial_history_boundary", "no MT5 bars in requested range")
    if not filtered["_timestamp"].is_monotonic_increasing or filtered["_timestamp"].duplicated().any():
        _fail_paginated(manifest, manifest_path, "integrity_failed", "MT5 history is not strictly chronological")
    expected_seconds = TIMEFRAME_SECONDS[timeframe.upper()]
    if (filtered["time"].astype("int64") % expected_seconds != 0).any():
        _fail_paginated(manifest, manifest_path, "integrity_failed", "MT5 history timestamps are not aligned to timeframe")

    manifest["filtered_bars"] = len(filtered)
    manifest["obtained_start"] = filtered["_timestamp"].iloc[0].isoformat()
    manifest["obtained_end"] = filtered["_timestamp"].iloc[-1].isoformat()
    manifest["gaps"] = _detect_gaps(filtered["_timestamp"], expected_seconds)
    manifest["gap_count"] = len(manifest["gaps"])
    manifest["status"] = "complete" if reached_start else "partial_history_boundary"
    csv_path = _write_paginated_export(filtered, output, metadata)
    manifest["csv_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    _write_manifest(manifest, manifest_path)
    return PaginatedHistoryExport(csv_path=csv_path, manifest_path=manifest_path, manifest=manifest)


def _write_export(rates: Any, output: str | Path, metadata: InstrumentPriceMetadata) -> Path:
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
    spread_points = source["spread"].fillna(0) if "spread" in source else 0

    exported = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(source["time"], unit="s", utc=True),
            "open": source["open"],
            "high": source["high"],
            "low": source["low"],
            "close": source["close"],
            "volume": volume,
            "spread_points": spread_points,
            "point_size": metadata.point_size,
            "tick_size": metadata.tick_size,
            "spread_price": spread_points * metadata.point_size,
        }
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    exported.to_csv(output_path, index=False)
    return output_path


def _write_paginated_export(
    source: pd.DataFrame, output: str | Path, metadata: InstrumentPriceMetadata
) -> Path:
    tick_volume = source["tick_volume"].fillna(0)
    real_volume = source["real_volume"].fillna(0)
    exported = pd.DataFrame(
        {
            "timestamp": source["_timestamp"],
            "open": source["open"],
            "high": source["high"],
            "low": source["low"],
            "close": source["close"],
            "volume": real_volume.where(real_volume > 0, tick_volume),
            "spread_points": source["spread"].fillna(0),
            "point_size": metadata.point_size,
            "tick_size": metadata.tick_size,
            "spread_price": source["spread"].fillna(0) * metadata.point_size,
        }
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    try:
        exported.to_csv(temporary, index=False)
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path


def _pagination_manifest(
    *, symbol: str, timeframe: str, start: datetime, end: datetime, page_size: int,
    include_current_bar: bool, require_complete: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "aqtf_mt5_paginated_history.v2",
        "symbol": symbol,
        "timeframe": timeframe.upper(),
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "obtained_start": None,
        "obtained_end": None,
        "snapshot_time_utc": datetime.now(timezone.utc).isoformat(),
        "page_size": page_size,
        "include_current_bar": include_current_bar,
        "require_complete": require_complete,
        "raw_bars": 0,
        "filtered_bars": 0,
        "unique_bars": 0,
        "duplicate_bars": 0,
        "conflicting_duplicates": 0,
        "gaps": [],
        "gap_count": 0,
        "pages": [],
        "csv_sha256": None,
        "status": None,
        "errors": [],
    }


def instrument_price_metadata(gateway: Any, symbol: str) -> InstrumentPriceMetadata:
    info = gateway.symbol_info(symbol)
    if info is None:
        raise MT5HistoryError(f"MT5 symbol is unavailable: {symbol}")
    point_size = getattr(info, "point", None)
    tick_size = getattr(info, "trade_tick_size", getattr(info, "tick_size", None))
    if not _positive_finite(point_size):
        raise MT5HistoryError(f"MT5 symbol metadata lacks a valid point_size: {symbol}")
    if not _positive_finite(tick_size):
        raise MT5HistoryError(f"MT5 symbol metadata lacks a valid tick_size: {symbol}")
    return InstrumentPriceMetadata(point_size=float(point_size), tick_size=float(tick_size))


def _positive_finite(value: Any) -> bool:
    try:
        return isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def _write_range_manifest(
    *,
    manifest_out: Path,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    csv_path: Path,
    metadata: InstrumentPriceMetadata,
) -> None:
    exported = pd.read_csv(csv_path)
    timestamps = pd.to_datetime(exported["timestamp"], utc=True, errors="raise")
    manifest = {
        "schema_version": "aqtf_mt5_range_history.v2",
        "symbol": symbol,
        "timeframe": timeframe.upper(),
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "obtained_start": timestamps.iloc[0].isoformat(),
        "obtained_end": timestamps.iloc[-1].isoformat(),
        "raw_bars": len(exported),
        "filtered_bars": len(exported),
        "price_unit_contract": metadata.as_manifest(),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "status": "complete",
        "errors": [],
    }
    _write_manifest(manifest, manifest_out)


def _page_manifest(start_pos: int, requested_count: int, rates: Any, last_error: Any) -> dict[str, Any]:
    return {
        "start_pos": start_pos,
        "requested_count": requested_count,
        "received_count": 0 if rates is None else len(rates),
        "page_start": None,
        "page_end": None,
        "last_error": last_error,
    }


def _last_error(gateway: Any) -> Any:
    value = gateway.last_error()
    return list(value) if isinstance(value, tuple) else value


def _terminal_maxbars(gateway: Any) -> int | None:
    terminal_info = getattr(gateway, "terminal_info", None)
    if not callable(terminal_info):
        return None
    info = terminal_info()
    maxbars = getattr(info, "maxbars", None)
    return int(maxbars) if isinstance(maxbars, int) and maxbars > 0 else None


def _detect_gaps(timestamps: pd.Series, expected_seconds: int) -> list[dict[str, Any]]:
    gaps = []
    for previous, current in zip(timestamps.iloc[:-1], timestamps.iloc[1:]):
        delta = int((current - previous).total_seconds())
        if delta > expected_seconds:
            gaps.append(
                {
                    "after": previous.isoformat(),
                    "before": current.isoformat(),
                    "delta_seconds": delta,
                    "missing_bars_estimate": max(delta // expected_seconds - 1, 0),
                    "classification": "unclassified_gap",
                }
            )
    return gaps


def _write_manifest(manifest: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _fail_paginated(manifest: dict[str, Any], path: Path, status: str, message: str) -> None:
    manifest["status"] = status
    manifest["errors"].append(message)
    _write_manifest(manifest, path)
    raise MT5HistoryError(message)


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
    manifest_out: str | Path | None = None,
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
            manifest_out=manifest_out,
        )
    finally:
        gateway.shutdown()


def export_paginated_from_local_terminal(
    *,
    symbol: str,
    timeframe: str,
    start: str | datetime,
    end: str | datetime,
    output: str | Path,
    manifest_out: str | Path,
    page_size: int = 5_000,
    include_current_bar: bool = False,
    require_complete: bool = True,
    gateway: Any | None = None,
) -> PaginatedHistoryExport:
    if gateway is None:
        try:
            import MetaTrader5 as gateway
        except ImportError as exc:
            raise MT5HistoryError("MetaTrader5 package is unavailable") from exc

    if not gateway.initialize():
        manifest = _pagination_manifest(
            symbol=symbol,
            timeframe=timeframe,
            start=_parse_utc(start),
            end=_parse_utc(end),
            page_size=page_size,
            include_current_bar=include_current_bar,
            require_complete=require_complete,
        )
        _fail_paginated(
            manifest,
            Path(manifest_out),
            "environment_blocked",
            f"MT5 terminal is unavailable: {_last_error(gateway)}",
        )
    try:
        return export_mt5_history_paginated(
            gateway,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            output=output,
            manifest_out=manifest_out,
            page_size=page_size,
            include_current_bar=include_current_bar,
            require_complete=require_complete,
        )
    finally:
        gateway.shutdown()
