from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from trading_bot.research import vrt_execution


def _bars(count: int = 130) -> list[dict]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(count):
        close = 100.0 + index * 0.1
        width = 20.0 if index in {64, 100} else 1.0
        rows.append({
            "timestamp_utc": base + timedelta(minutes=5 * index), "symbol": "XAUUSD", "timeframe": "M5",
            "open_bid": close - 0.1, "high_bid": close + width / 2, "low_bid": close - width / 2,
            "close_bid": close, "spread_points": 10.0, "point_size": 0.01, "is_completed": True,
        })
    return rows


def test_execution_is_read_only_preserves_artifacts_and_reconciles_synthetic_run(tmp_path):
    result = vrt_execution.execute_frozen_vrt(_bars(), output_root=tmp_path, command="synthetic-vrt")

    manifest = json.loads((Path(result["output_directory"]) / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["order_api_called"] is False
    assert manifest["real_data_observed"] is False
    assert manifest["artifact_hashes"]
    assert result["event_funnel"]["raw_event_count"] >= result["trade_funnel"]["trade_count"]
    assert result["predictor_matrix"]["predictors"] == list(vrt_execution.STRICT_PREDICTORS)
    assert (Path(result["output_directory"]) / "first_observation_record.json").exists()
