from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_bot.research import tcap_execution
from tests.test_trend_continuation_after_pullback import (
    _long_pullback_fixture,
)


def _frozen_universe_fixture() -> list[dict]:
    rows = []
    for stream in (
        "XAUUSD:M5",
        "XAUUSD:M15",
        "XAUUSD:H1",
        "EURUSD:M5",
        "EURUSD:M15",
        "GBPUSD:M5",
        "GBPUSD:M15",
        "US30:M5",
        "US30:M15",
    ):
        symbol, timeframe = stream.split(":")
        for row in _long_pullback_fixture():
            rows.append({**row, "symbol": symbol, "timeframe": timeframe})
    return rows


def test_execution_is_append_only_read_only_and_writes_auditable_artifacts(tmp_path):
    result = tcap_execution.execute_frozen_tcp(
        _frozen_universe_fixture(),
        output_root=tmp_path,
        command="synthetic-tcp",
    )
    run = Path(result["output_directory"])
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["order_api_called"] is False
    assert manifest["mt5_write_api_called"] is False
    assert manifest["artifact_hashes"]
    assert manifest["terminal_funnel_reconciled"] is True
    assert set(manifest["gate_report"]) == set(tcap_execution.STRICT_PREDICTORS)
    assert (run / "first_observation_record.json").exists()


def test_linear_feature_cache_matches_reference_and_excludes_outcome_fields():
    rows = _long_pullback_fixture()
    cache = tcap_execution.precompute_feature_rows(rows)
    for index in range(len(rows)):
        assert cache[index] == tcap_execution.feature_row_reference(
            rows[: index + 1], direction="long", pullback_depth=0.2, pullback_duration=2
        )
    assert set(tcap_execution.STRICT_PREDICTORS).isdisjoint(
        tcap_execution.OUTCOME_ONLY_FIELDS
    )


def test_execution_rejects_an_unfrozen_universe(tmp_path):
    rows = _long_pullback_fixture()
    for row in rows:
        row["symbol"] = "NOT_FROZEN"
    with pytest.raises(ValueError, match="universe"):
        tcap_execution.execute_frozen_tcp(
            rows, output_root=tmp_path, command="invalid-universe"
        )
