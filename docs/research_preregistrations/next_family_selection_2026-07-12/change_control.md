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
