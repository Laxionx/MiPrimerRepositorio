# Forbidden actions and change-control policy

After any results are observed, the following actions are forbidden for this family:

- changing the detector or its parameters;
- changing thresholds, features, symbols, timeframes, development period, temporal
  split, minimum support, stability gates, spread/slippage assumptions, SL, or TP;
- combining failed predictors, adding interactions, or introducing machine learning;
- selecting favorable subgroups, reclassifying near-passes as candidates, or using
  Liquidity Sweep evidence for tuning or rescue.

Any such change must be declared as a separately versioned new hypothesis with a new
family or hypothesis ID. It invalidates confirmatory interpretation of the previous
result and does not permit retroactive reuse of its results.

## Fixed execution and outcome controls

- **Detector:** after 64 valid completed bars, detect only when
  `atr_ratio_14_56(t) >= 1.20` and `atr_ratio_14_56(t-1) < 1.20`.
- **Direction:** long when `close_t > close_t-8`; short when `close_t < close_t-8`;
  exclude equality. Direction is an outcome-measurement convention, not a changed
  detector threshold.
- **Data quality:** exclude a setup if any required field is missing, non-finite,
  non-positive where a denominator is required, or if the current high-low range is
  greater than 20 times the median range of the preceding 56 completed bars. Do not
  impute or winsorize.
- **Overlap:** one active outcome per symbol/timeframe; suppress later detections until
  its first exit or the fixed 48-bar maximum holding horizon.
- **Costs:** `spread_price = next_bar_spread_points * point_size`; fixed adverse
  slippage is `0.25 * spread_price` per entry and exit. Long entry is next-bar ask
  open plus slippage; short entry is next-bar bid open minus slippage.
- **Stops and targets:** risk is `1.50 * atr_14_points` at decision time; target is
  `2.00 * risk`; prices use the direction and effective entry above. If both stop and
  target occur in one bar, record stop first. If neither occurs by 48 completed bars,
  exit at the cost-adjusted close of bar 48.
- **Data gaps:** exclude a setup when any required interval between bars exceeds three
  nominal bar durations; never bridge, synthesize, or replace it.

## Gates and approval rule

The primary outcome is cost-adjusted R per setup. Minimum support requires at least
600 development setups, 300 internal-validation setups, and at least 30 internal
setups in each of five distinct symbol/timeframe runs. Stability requires non-negative
median R in at least five of nine runs and no run below -0.20 median R with at least
30 internal setups. Mandatory train/test conditions are non-negative mean R and
non-negative median R in both periods, with internal mean R not less than -0.05.

There are eight predeclared descriptive features. Any feature-level inference uses a
two-sided familywise alpha of `0.00625` (Bonferroni); it cannot modify the detector or
create a rule. A scorecard passes only if every support, stability, temporal, cost,
and multiplicity condition passes. A passing retrospective scorecard creates at most a
Candidate Discriminator Hypothesis. Final approval requires the unchanged three-month
prospective replication to pass the same gates; no Candidate Rule Report is created by
this package.

Family closure is mandatory when the scorecard fails any required gate or the
prospective replication fails. Closure preserves artifacts and forbids rescue under
this family ID.

## Canonical outcome and cost contract

This section is normative and supersedes any shorter summary above. Source OHLC is bid
price. For each bar `b`, `spread_price_b = spread_points_b * point_size`; `point_size`
is the sole spread conversion unit. `tick_size` is never substituted for it. Fixed
adverse `slippage_price_b = 0.25 * spread_price_b`, in price units, applies at each
entry and exit.

For an event decided at completed bar `t`, measurement is at next completed bar
`e=t+1`. Long effective entry is `open_bid_e + spread_price_e + slippage_price_e`;
short effective entry is `open_bid_e - slippage_price_e`. Direction is fixed by the
detector: `long` for `close_t > close_(t-8)`, `short` for the strict inverse, and no
measurement for equality. Risk denominator `risk_price = 1.50 * atr_14_points_t` must
be finite and positive. Long stop/target are `entry-risk_price` and
`entry+2*risk_price`; short stop/target are `entry+risk_price` and
`entry-2*risk_price`. Non-positive post-cost geometry is
`excluded_post_cost_geometry`.

For a later bar `b`, long TP/SL use `high_bid_b >= target` and `low_bid_b <= stop`.
Short TP/SL use `low_bid_b + spread_price_b <= target` and
`high_bid_b + spread_price_b >= stop`. If both conditions are true in one bar, SL is
first. Effective long exit is gross exit price minus `slippage_price_b`; effective
short exit is gross exit price plus `slippage_price_b`. At bar 48 with no TP/SL, use
the cost-adjusted bid close (long: `close_bid-slippage`; short:
`close_bid+spread_price+slippage`). A gap or unavailable required bar during an active
measurement produces `data_unavailable`, not an assumed fill.

Price PnL per unit is `direction_sign * (effective_exit-effective_entry)`, where long
is `+1` and short is `-1`. Per-trade `R = price_pnl_per_unit / risk_price`; any
monetary PnL audit must reconcile as monetary price PnL divided by the same risk
denominator after its recorded contract/volume conversion. Breakeven is only an exact
zero effective PnL time exit; there is no discretionary breakeven exit.

Each raw detector event has the canonical event ID in `detector_semantics.md`.
Measurement/trade ID is SHA-256 of `event_id|entry_timestamp_utc|outcome_policy=v1`.
Each raw event appears once in the terminal funnel: `invalid_input`,
`no_direction`, `excluded_post_cost_geometry`, `suppressed_overlap`,
`data_unavailable`, `duplicate_event`, `tp`, `sl`, or `time_exit_48`. The count of raw
events equals the sum of these mutually exclusive categories. No terminal category,
cost, stop, target, R formula, or holding rule may change after results are observed.

The first observation and defect policies in
`activation_conformance_observation_policy.md` apply to every outcome run and prevent
replacement of unfavorable or invalidated evidence.
