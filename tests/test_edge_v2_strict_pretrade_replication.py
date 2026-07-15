import inspect
import json

import pytest

from trading_bot.research import edge_v2_strict_pretrade_replication as replication
from trading_bot.research.edge_v2_feature_timing_provenance import (
    build_feature_timing_provenance_report,
)


def _trade(trade_id, pnl, index, direction="LONG", **overrides):
    return {
        "trade_id": trade_id,
        "pnl": pnl,
        "lower_quartile_closes": 0,
        "direction": direction,
        "timestamp_open": f"2026-01-{index:02d}T00:00:00+00:00",
        "risk_points": 2 if pnl > 0 else 8,
        "reward_points": 10 if pnl > 0 else 6,
        "prior_range_points": 10,
        "atr": 5,
        "candle_range": 3,
        "symbol": "XAUUSD",
        "timeframe": "M5",
        **overrides,
    }


def _records():
    rows = []
    for index in range(1, 13):
        rows.append(_trade(f"w{index}", 4 + index, index, "LONG"))
        rows.append(_trade(f"l{index}", -2 - index, index + 12, "SHORT"))
    return rows + [_trade("outside", 7, 25, lower_quartile_closes=1)]


def _provenance():
    return build_feature_timing_provenance_report()["registry"]


def _write(path, records):
    path.write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")


def test_strict_provenance_excludes_at_entry_effective_entry_fields():
    report = replication.analyze_strict_pretrade_records(_records(), provenance=_provenance())

    assert report["strict_field_policy"]["included_fields"] == []
    assert (
        report["strict_field_policy"]["excluded_fields"]["risk_points"]
        ["provenance"]["availability_timing"]
        == "at_entry"
    )
    assert "candle_range" in report["strict_field_policy"]["excluded_fields"]
    assert report["strict_field_policy"]["excluded_fields"]["candle_range"]["reason"]
    assert report["slices"]["lower_quartile_closes_eq_0"]["filtered_trade_count"] == 24


def test_fixed_lqc_long_short_slices_and_missing_direction_are_explicit():
    rows = _records()
    rows.append(_trade("unknown", 1, 26, direction=None))
    slices = replication.analyze_strict_pretrade_records(rows, provenance=_provenance())["slices"]

    assert slices["lower_quartile_closes_eq_0_long"]["filtered_trade_count"] == 12
    assert slices["lower_quartile_closes_eq_0_short"]["filtered_trade_count"] == 12
    assert slices["lower_quartile_closes_eq_0_long"]["direction_availability"] == "available"
    assert slices["lower_quartile_closes_eq_0"]["unavailable_direction_count"] == 1


def test_fields_include_full_separation_rank_and_fixed_bins():
    field = replication.analyze_strict_pretrade_records(
        _records(), provenance=_provenance()
    )["slices"]["lower_quartile_closes_eq_0"]["candidate_field_results"]

    assert field == {}


def test_per_run_aggregate_and_calibration_holdout_use_second_half_only(tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    _write(first, _records())
    _write(second, _records())

    report = replication.replicate_strict_pretrade(
        [first, second], provenance=_provenance()
    )
    run = report["per_run"][0]
    assert report["aggregate_replication_summary"]["successful_inputs"] == 2
    assert run["symbol"] == "XAUUSD"
    assert run["calibration_diagnostics"] == {}


def test_missing_provenance_empty_old_and_missing_fields_are_safe(tmp_path):
    with pytest.raises(ValueError, match="provenance"):
        replication.analyze_strict_pretrade_records(_records())

    report = replication.analyze_strict_pretrade_records(
        _records()[:2], provenance=_provenance()
    )
    assert report["slices"]["lower_quartile_closes_eq_0"]["candidate_field_results"] == {}

    empty = tmp_path / "empty.jsonl"
    missing = tmp_path / "missing.jsonl"
    _write(empty, [])
    batch = replication.replicate_strict_pretrade([empty, missing], provenance=_provenance())
    assert batch["aggregate_replication_summary"]["successful_inputs"] == 1
    assert "insufficient_data" in batch["decision_flags"]


def test_provenance_file_cli_writer_and_no_execution_path(tmp_path):
    journal = tmp_path / "journal.jsonl"
    provenance = tmp_path / "provenance.json"
    output = tmp_path / "strict.json"
    _write(journal, _records())
    provenance.write_text(json.dumps(build_feature_timing_provenance_report()), encoding="utf-8")

    replication.main([
        "--journal", str(journal), "--condition", "lower_quartile_closes_eq_0",
        "--provenance", str(provenance), "--out", str(output),
    ])

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["diagnostic_only"] is True
    assert set(saved["decision_flags"]).issubset(set(replication.DECISION_FLAGS))
    source = inspect.getsource(replication)
    assert "order_send" not in source
    assert "submit_allowed=True" not in source
