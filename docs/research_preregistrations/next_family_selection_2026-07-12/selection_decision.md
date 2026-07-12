# Selection decision record

- **Decision ID:** `next-family-selection-20260712`
- **Base commit:** `c3f4742ea85781734b17320db8f4406a4f6e9b78`
- **Method:** fixed, equally weighted 0-3 rubric defined before scoring.
- **Selected family:** Volatility Regime Transition.
- **Family ID:** `volatility-regime-transition-vrt-20260712-v1`.
- **Decision basis:** total 27/30; next-ranked candidate 23/30; no disqualifying
  criterion score.

The provisional lead was not selected automatically. It won the locked rubric based
on methodological independence, completed-bar observability, data requirements,
falsifiability, and auditability. No candidate performance, profitability, backtest,
MT5 query, trade generation, or order API was used.

## Activation and blockers

There are no material *parameter* blockers: every methodological parameter necessary
for a first execution is fixed in the preregistration. The following are mandatory
activation gates, not unresolved discretion:

1. Review and merge of this documentation package.
2. A separate implementation commit that identifies this family ID, preserves every
   frozen parameter, and passes the required test/provenance checks.
3. A separately recorded execution commit and manifest before any data execution.
4. Accumulation of the declared prospective independent validation interval before
   any final edge or profitability claim.

Until those gates are met, Volatility Regime Transition is not active research. A
development or internal-validation result may at most create a candidate hypothesis;
it cannot confirm an edge or profitable strategy.
