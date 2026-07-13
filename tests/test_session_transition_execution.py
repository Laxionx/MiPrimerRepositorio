from __future__ import annotations

import json
from pathlib import Path

from trading_bot.research import session_transition_execution as execution
from tests.test_session_transition import _london_fixture


def _frozen_universe() -> list[dict]:
    rows = []
    for stream in ("XAUUSD:M5", "XAUUSD:M15", "XAUUSD:H1", "EURUSD:M5", "EURUSD:M15", "GBPUSD:M5", "GBPUSD:M15", "US30:M5", "US30:M15"):
        symbol, timeframe = stream.split(":")
        rows.extend({**row, "symbol": symbol, "timeframe": timeframe} for row in _london_fixture())
    return rows


def test_execution_is_append_only_read_only_and_cached(tmp_path):
    result = execution.execute_frozen_session_transition(_frozen_universe(), output_root=tmp_path, command="synthetic-session")
    manifest = json.loads((Path(result["output_directory"]) / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["order_api_called"] is False
    assert manifest["terminal_funnel_reconciled"] is True
    assert set(manifest["gate_report"]) == set(execution.STRICT_PREDICTORS)
    assert manifest["invariants"]["strict_predictor_matrix_exact"] is True


def test_cached_features_match_reference_for_each_eligible_row():
    rows = _london_fixture()
    cache = execution.precompute_indicator_rows(rows)
    for index in range(len(rows)):
        assert cache[index] == execution.indicator_row_reference(rows[:index + 1])
