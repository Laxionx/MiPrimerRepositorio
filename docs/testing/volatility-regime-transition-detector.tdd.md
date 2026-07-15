# Volatility Regime Transition detector - TDD evidence

Source journeys were derived from the merged PR #28 preregistration rather than a
separate plan file. The implementation is synthetic-only and keeps execution disabled.

- **RED:** `python -m pytest tests/test_volatility_regime_transition.py -q` failed at
  collection because `trading_bot.research.volatility_regime_transition` did not exist.
- **GREEN:** the same target passed with `18 passed` after the deterministic detector,
  manifest conformance, provenance, event-ID, overlap, and audit code was added.
- **Focused provenance integration:** `66 passed` from the VRT and existing focal
  provenance/research suites.
- **Coverage:** `python -m pytest tests/test_volatility_regime_transition.py
  --cov=trading_bot.research.volatility_regime_transition --cov-report=term-missing -q`
  reported 83% module coverage.

| Guarantee | Test target | Result |
|---|---|---|
| Frozen manifest constants and feature matrix fail closed on mismatch | `test_manifest_conformance_and_registry_are_frozen`, `test_manifest_missing_or_changed_parameter_fails_closed` | PASS |
| Threshold, warm-up, same-bar confirmation, reset, and re-arm semantics are deterministic | threshold/state tests | PASS |
| Missing/gapped streams reset before re-warm; event IDs/order and duplicate/overlap handling are deterministic | event stream tests | PASS |
| Strict features reject late or unregistered dependencies | `test_strict_provenance_rejects_late_unknown_or_unregistered_dependencies` | PASS |
| Audit schema is execution-disabled and reconciles terminals | `test_audit_schema_is_execution_disabled_and_has_terminal_reconciliation` | PASS |

No MT5 connection, real data, backtest, performance inspection, order API, or
prospective activation was used in the RED/GREEN cycle.
