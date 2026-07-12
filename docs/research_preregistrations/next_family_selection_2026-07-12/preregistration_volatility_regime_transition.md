# Preregistration: Volatility Regime Transition

**Family ID:** `volatility-regime-transition-vrt-20260712-v1`

**Status:** draft; inactive until reviewed and merged.

**Scope:** documentation only; no detector implementation, market-data access,
backtest, trade generation, or execution has occurred.

1. **Family identity:** `Volatility Regime Transition`, family ID
   `volatility-regime-transition-vrt-20260712-v1`.
2. **Question:** Does the frozen completed-bar volatility-transition setup satisfy the
   declared cost-aware temporal gates? No profitability assumption is made.
3. **Mechanism:** a transition from compressed to expanding realized volatility may
   alter subsequent directional movement distribution.
4. **Falsification:** failure of any declared support, stability, temporal, cost,
   multiplicity, or prospective-replication gate closes this family version.
5. **Prior-work separation:** no Liquidity Sweep detector, fields, results, or rescue
   logic is permitted.
6. **Permitted data:** only local MT5 UTC OHLC/spread/point-size bars as specified in
   the contamination-boundary document.
7. **Universe:** XAUUSD M5/M15/H1, EURUSD M5/M15, GBPUSD M5/M15, US30 M5/M15.
8. **Development period:** `2026-01-01T00:00:00Z` through `2026-04-30T23:59:59Z`.
9. **Internal validation period:** `2026-05-01T00:00:00Z` through
   `2026-07-10T21:00:00Z`.
10. **Prospective policy:** begins only at the non-backdated UTC activation timestamp
    after all seven activation requirements; it ends after three complete calendar
    months and no final confirmation may precede it.
11. **Decision timestamp:** close of fully completed bar `t`; all discovery inputs must
    be known by that close.
12. **Detector:** after 64 valid bars, `atr_ratio_14_56(t) >= 1.20` and
    `atr_ratio_14_56(t-1) < 1.20`.
13. **Detector parameters:** Wilder ATR 14 and 56; threshold 1.20; prior-comparison
    lag one bar; maximum holding 48 bars.
14. **Candidate features:** `atr_14_points`, `atr_56_points`, `atr_ratio_14_56`,
    `atr_ratio_change_8`, `mean_range_8_points`, `mean_range_56_points`,
    `range_ratio_8_56`, and `efficiency_20`; no additions or interactions.
15. **Timing classification:** every listed candidate feature is `pre_decision`.
16. **Dependencies:** every derived feature has the exact `depends_on_fields` mapping
    in `feature_provenance_plan.md`; a missing or excluded dependency fails closed.
17. **Strict eligibility:** complete source-backed provenance, `pre_decision` timing,
    low leakage risk, and no direct/transitive excluded input are all required.
18. **Excluded fields:** all entry/cost/outcome/future fields and all Liquidity Sweep
    fields listed in the provenance plan.
19. **Missing data:** exclude; no imputation.
20. **Outliers:** exclude only predeclared invalid/non-finite and 20x prior-56
    median-range cases; no outcome trimming or winsorization.
21. **Setup inclusion/exclusion:** include only valid detector, nonzero direction,
    valid costs, and no data gap; exclude every failed condition or active overlap.
22. **Position overlap:** one active outcome per symbol/timeframe until exit or bar 48.
23. **Spread contract:** next-bar MT5 spread points multiplied by symbol point size.
24. **Slippage contract:** fixed adverse `0.25 * spread_price` on entry and exit.
25. **Outcome entry timing:** cost-adjusted next-bar open after the decision timestamp.
26. **Stop/target policy:** `1.50 * atr_14_points` risk and `2.00 * risk` target.
27. **Ambiguous TP/SL:** when both occur in one bar, stop is first.
28. **Data gaps:** exclude gaps exceeding three nominal bar durations.
29. **Temporal split:** the fixed development and internal intervals above; no
    reshuffling or post-result boundary changes.
30. **Minimum-support gates:** 600 development setups, 300 internal setups, and five
    runs with at least 30 internal setups.
31. **Stability gates:** non-negative median R in five of nine runs and no qualifying
    run below -0.20 median R.
32. **Mandatory train/test conditions:** non-negative mean and median R in both
    periods; internal mean R at least -0.05.
33. **Multiple comparisons:** eight descriptive features; two-sided Bonferroni alpha
    0.00625; feature inference cannot modify the detector.
34. **Scorecard/final approval:** every support, stability, temporal, cost, and
    multiplicity gate must pass; final approval also requires item 36.
35. **Candidate-hypothesis policy:** only a fully passing retrospective scorecard may
    create a Candidate Discriminator Hypothesis, never a trading rule.
36. **Independent replication:** unchanged three-complete-month prospective replication
    is mandatory for any final edge/profitability evaluation.
37. **Formal closure:** failure of any mandatory gate closes this family version.
38. **Forbidden post-result actions:** `change_control.md` applies verbatim; any change
    creates a separately versioned hypothesis and invalidates confirmation.
39. **Required artifacts/manifests:** deterministic plan, provenance registry, input
    manifests, detector audit, setup journal, temporal audit, scorecard, and
    closure/evidence manifest; raw data remains outside Git.
40. **Required code/execution commits:** separate implementation and execution commits
    must record this family ID, base, manifest hash, and tests before data execution.
    Their future SHAs are activation records, not unfixed methodological parameters.

## Canonical semantic and activation documents

`detector_semantics.md`, `feature_provenance_plan.md`, `change_control.md`, and
`activation_conformance_observation_policy.md` are normative parts of this
preregistration. They freeze the event stream, feature registry, outcome contract,
seven-step activation boundary, implementation conformance, first-observation record,
and post-observation defect policy. Their machine-readable equivalents are in the
manifest; a disagreement fails closed and blocks execution.

Volatility Regime Transition generates its event population directly from the
volatility state machine. It must not consume or filter Liquidity Sweep candidates,
setups, trades, winners, losers, or favorable cohorts; it does not require a sweep
event and cannot be a rescue filter. Chance timestamp overlap does not alter this
independence. Liquidity Sweep remains formally closed.

The previously inspected `atr`, `atr_contraction_pct`, `compression_score`, and
related ATR/range concepts appear only where justified by this preregistered volatility
mechanism. Prior Liquidity Sweep effects did not motivate their inclusion or parameter
values and cannot support this family. The entire `2026-01-01T00:00:00Z` through
`2026-07-10T21:00:00Z` interval is contaminated: success there can create only a
Candidate Discriminator Hypothesis, never confirmation. Confirmed edge requires
post-activation independent prospective evidence.
