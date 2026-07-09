# AQTF Edge V2 Foundation — TDD Evidence

## Source

User journeys and acceptance criteria were provided directly for this change;
no external plan file was used.

## User journeys

- As a researcher, I can compare compression and directional-pressure diagnostics
  across winning and losing liquidity-sweep trades without changing the strategy.
- As an operator, I can retain those diagnostics for completed and blocked setups.
- As an analyst, I can continue to review older journals that predate Edge V2.

## RED / GREEN evidence

| Stage | Command | Result |
|---|---|---|
| RED | `python -m pytest tests/test_edge_v2.py tests/test_trade_journal.py tests/test_output.py tests/test_trade_review.py tests/test_trade_segmentation.py -q` | Failed during collection because `trading_bot.analysis.edge_v2` did not exist. |
| GREEN | Same targeted command | `21 passed in 3.21s`. |
| Full suite | `python -m pytest tests -q` | `76 passed in 2.03s`. |
| Coverage | `python -m pytest tests --cov=trading_bot --cov-report=term-missing -q` | `76 passed`; repository total 83%, `edge_v2.py` 95%. |

## Guarantees

| # | Guarantee | Test evidence |
|---|---|---|
| 1 | Compression score rises when recent candle ranges contract and clear contraction is marked as compressing. | `tests/test_edge_v2.py` |
| 2 | Upper- and lower-quartile close clustering produces long and short pressure; neutral remains possible. | `tests/test_edge_v2.py` |
| 3 | Insufficient candle history produces unknown (`null`) diagnostics. | `tests/test_edge_v2.py` |
| 4 | Completed-trade and blocked-setup journals retain all Edge V2 diagnostic fields. | `tests/test_trade_journal.py` |
| 5 | Older journals without Edge V2 fields still load. | `tests/test_trade_segmentation.py` |
| 6 | Best-vs-worst reports and CSV exports include Edge V2 numeric and categorical diagnostics. | `tests/test_trade_review.py` |
| 7 | Analysis-only safety fields remain unchanged. | `tests/test_output.py` |

## Scope guard

Edge V2 is computed in a dedicated diagnostics module and is appended to output,
journal, and review data only. It does not modify `EntryScorer`, `RiskGuard`,
order submission, demo/paper execution, or threshold configuration.

## Lint and compilation

- `python -m ruff check <Edge V2 changed files>`: passed.
- `python -m compileall -q trading_bot scripts`: passed.
- Full-repository Ruff remains blocked by six pre-existing violations in untouched
  files (`tests/test_config.py`, `trading_bot/core/interfaces.py`,
  `trading_bot/data/mt5_data.py`, and `trading_bot/signals/liquidity_sweep.py`).
