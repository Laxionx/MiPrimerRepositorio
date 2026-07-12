# Commands executed

All commands ran in a clean temporary worktree at
`5a8c2f51fe0294a742ec04460338eddbe7d9f493`. Output was written outside the
repository under the original temporary evidence directory.

```powershell
python -m trading_bot.research.edge_v2_mt5_batch --plan <batch_plan.json> `
  --out-dir <batch> --strict --history-mode paginated --page-size 5000

python -m trading_bot.research.edge_v2_feature_timing_provenance `
  --batch-dir <batch> --out <edge_v3/provenance.json>
python -m trading_bot.research.edge_v3_pretrade_feature_matrix `
  --batch-dir <batch> --provenance <provenance.json> `
  --out <edge_v3/matrix.json> --manifest-out <edge_v3/matrix_manifest.json>
python -m trading_bot.research.edge_v3_full_pretrade_discriminator_discovery `
  --matrix <matrix.json> --out <edge_v3/discovery.json>
python -m trading_bot.research.edge_v3_temporal_train_test_audit `
  --matrix <matrix.json> --discovery <discovery.json> --out <edge_v3/temporal.json>
python -m trading_bot.research.edge_v3_robustness_scorecard `
  --matrix <matrix.json> --discovery <discovery.json> --train-test <temporal.json> `
  --out <edge_v3/scorecard.json> --summary-out <edge_v3/summary.md>
python -m trading_bot.research.edge_v4_setup_failure_audit `
  --batch-dir <batch> --out <edge_v3/edge_v4_descriptive_audit.json> `
  --detail-out <edge_v3/edge_v4_descriptive_trade_detail.json>
```

Validation executed against the canonical worktree:

```powershell
python -m pytest tests/test_edge_v2_feature_timing_provenance.py `
  tests/test_edge_v2_strict_pretrade_replication.py tests/test_edge_v3_research_pipeline.py `
  tests/test_edge_v4_setup_failure_audit.py tests/test_backtest.py `
  tests/test_backtest_price_units.py tests/test_mt5_history_pipeline.py `
  tests/test_edge_v2_mt5_pipeline.py tests/test_edge_v2_mt5_batch.py -q
# 114 passed

python -m pytest tests -q        # 209 passed
python -m compileall -q trading_bot
python -m ruff check <established focal scope>
git diff --check
```

The MT5 terminal was queried only for read-only history and identification. No live
order API was invoked; batch metadata records `submit_allowed: false` and
`broker_api_called: false`.
