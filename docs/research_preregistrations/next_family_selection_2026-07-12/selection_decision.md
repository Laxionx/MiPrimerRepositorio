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

The methodological parameters are frozen, but the family has no current execution or
prospective-activation readiness. The mandatory activation gates are: merged
preregistration; reviewed/frozen implementation commit; reviewed/frozen finalized
provenance artifact; passing conformance tests; frozen execution configuration;
committed machine-readable activation record; and a non-backdated activation UTC
timestamp. Merging this PR alone does not activate the family or start prospective
validation.

Until those gates are met, Volatility Regime Transition is not active research. A
development or internal-validation result may at most create a candidate hypothesis;
it cannot confirm an edge or profitable strategy.

## Final execution decision — 2026-07-12

**Volatility Regime Transition CLOSED.** The frozen historical
development/internal-validation execution completed from its preserved input snapshot
without altering the preregistered configuration. Its immutable rerun record is
`vrt-run-d7cdf7db-0fd0-4c13-81ab-c4074b0d0901`; its run-manifest SHA-256 is
`bc97760faba1872adb1a364378227c6badbb5ebabc4506400af8f6ddae53d9e1`.

The rerun produced 2,224 detector events and 2,224 terminal trade records. The eight
strict predictors did not produce a Candidate Discriminator Hypothesis: the frozen
temporal and stability gates failed. Accordingly, no edge or profitable strategy was
found or confirmed, and no prospective confirmation was started. This closure applies
to `volatility-regime-transition-vrt-20260712-v1`; no successor family is started by
this record.
