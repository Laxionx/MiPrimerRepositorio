# Edge V2 MT5 Research Pipeline — TDD Evidence

## Source and journeys

This change was derived from the requested research-only MT5 follow-up. A
researcher can export local candle history, run the existing sequential backtest,
and produce an Edge V2 separation report without changing strategy or execution.

## RED / GREEN evidence

| Stage | Command | Result |
|---|---|---|
| RED | `python -m pytest tests/test_edge_v2_mt5_pipeline.py -q` | Failed because the MT5 research pipeline module did not exist. |
| GREEN | `python -m pytest tests/test_edge_v2_mt5_pipeline.py tests/test_mt5_history_pipeline.py -q` | `13 passed in 2.41s`. |
| Full suite | `python -m pytest tests -q` | `90 passed in 4.02s`. |
| Coverage | `python -m pytest tests --cov=trading_bot --cov-report=term-missing -q` | `90 passed`; repository total 83%. |

## Guarantees

| # | Guarantee | Test evidence |
|---|---|---|
| 1 | Historical MT5 ranges export through the existing MT5 history module. | `tests/test_mt5_history_pipeline.py` |
| 2 | The pipeline produces an MT5-labelled, analysis-only report with safety fields disabled. | `tests/test_edge_v2_mt5_pipeline.py` |
| 3 | Missing MT5 history raises a clean environment block and creates no report. | `tests/test_edge_v2_mt5_pipeline.py` |
| 4 | No pipeline or range-export code contains an execution path. | `tests/test_edge_v2_mt5_pipeline.py` |
| 5 | Strongest and weakest numeric feature effects are ranked only as diagnostics. | `tests/test_edge_v2_mt5_pipeline.py` |

## Local research evidence

The local terminal exported `XAUUSD` `M5` candles from
`2026-05-18T19:10:00+00:00` to `2026-07-10T01:40:00+00:00` and generated a local
report. Generated candles, journals, and reports are intentionally not committed.

## Scope guard

The pipeline only calls MT5 history APIs and the existing research backtest. It
does not change strategy, `RiskGuard`, execution, broker credentials, or live
trading behavior. Ruff passed on touched files and `compileall` passed.
