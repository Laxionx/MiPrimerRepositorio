# Edge V2 Feature Separation — TDD Evidence

## Source and journeys

This work was derived directly from the requested follow-up PR. It lets a
researcher compare existing Edge V2 journal variables across winning and losing
trades without changing strategy, risk, or execution behavior.

## RED / GREEN evidence

| Stage | Command | Result |
|---|---|---|
| RED | `python -m pytest tests/test_edge_v2_feature_separation.py -q` | Failed because `trading_bot.research` did not exist. |
| GREEN | Same targeted command | `9 passed in 1.10s`. |
| Full suite | `python -m pytest tests -q` | `85 passed in 2.90s`. |
| Coverage | `python -m pytest tests --cov=trading_bot --cov-report=term-missing -q` | `85 passed`; repository total 84%, report module 86%. |

## Guarantees

| # | Guarantee | Test evidence |
|---|---|---|
| 1 | Numeric Edge V2 fields have winner/loser statistics, effect size, interpretation, and top-vs-worst comparison. | `tests/test_edge_v2_feature_separation.py` |
| 2 | Older journals without Edge V2 columns and empty journals are safe. | `tests/test_edge_v2_feature_separation.py` |
| 3 | One-sided outcomes are marked insufficient; breakevens are excluded from both comparison groups. | `tests/test_edge_v2_feature_separation.py` |
| 4 | JSONL and CSV input records load, and the JSON output includes the report schema. | `tests/test_edge_v2_feature_separation.py` |
| 5 | Categorical pressure direction is reported as a distribution without a fabricated numeric effect size. | `tests/test_edge_v2_feature_separation.py` |

## Scope guard and validation

The report reads journals only. No strategy, `RiskGuard`, execution, or broker
code changed. `python -m ruff check trading_bot/research tests/test_edge_v2_feature_separation.py`
and `python -m compileall -q trading_bot` passed. Full-repository Ruff still has
the existing unrelated baseline violations outside this PR.
