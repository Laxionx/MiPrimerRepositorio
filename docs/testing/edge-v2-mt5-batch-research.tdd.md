# Edge V2 MT5 Batch Research — TDD Evidence

- RED: `tests/test_edge_v2_mt5_batch.py` failed because the batch module did not exist.
- GREEN: `4 passed`; full suite `94 passed`.
- Coverage: repository 83%; batch module 81%.

The tests cover JSON plan parsing, successful plus blocked runs, aggregate direction
consistency/stability, and absence of execution paths. The runner only orchestrates
existing MT5 history export, backtest, and feature-separation modules.
