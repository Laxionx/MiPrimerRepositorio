from __future__ import annotations

import json
from pathlib import Path

from trading_bot.research import tcap_execution
from tests.test_trend_continuation_after_pullback import _long_pullback_fixture, _short_pullback_fixture


def test_execution_is_append_only_read_only_and_writes_auditable_artifacts(tmp_path):
    result = tcap_execution.execute_frozen_tcp(
        _long_pullback_fixture() + _short_pullback_fixture(), output_root=tmp_path, command="synthetic-tcp"
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
        assert cache[index] == tcap_execution.feature_row_reference(rows[: index + 1], direction="long", pullback_depth=0.2, pullback_duration=2)
    assert set(tcap_execution.STRICT_PREDICTORS).isdisjoint(tcap_execution.OUTCOME_ONLY_FIELDS)
