# Data-contamination and validation boundary

## Known-used interval

`2026-01-01T00:00:00Z` through `2026-07-10T21:00:00Z` has already been used
extensively by the laboratory. It is not pristine independent validation for
Volatility Regime Transition and must never be described as such.

| Role | Fixed interval or policy | Allowed conclusion |
|---|---|---|
| Development | `2026-01-01T00:00:00Z` to `2026-04-30T23:59:59Z` | Specification/debug evidence only; no edge or profitability claim. |
| Internal temporal validation | `2026-05-01T00:00:00Z` to `2026-07-10T21:00:00Z` | Candidate-hypothesis evidence only after all gates; no edge or profitability claim. |
| Prospective independent validation | Begins only at the non-backdated activation UTC timestamp recorded after all seven activation requirements in `activation_conformance_observation_policy.md`; ends after three complete calendar months. | Required, unchanged independent replication before any final edge or profitability claim. |

Merging this preregistration alone does not start prospective validation. Data before
the activation timestamp, or collected while implementation semantics remain
changeable, is contaminated and cannot be prospective confirmation. The activation
timestamp cannot precede the activation-record commit and cannot be backdated. The
prospective period must be accumulated without detector, universe, feature, cost,
split, gate, or outcome-policy changes. If a material market-data gap occurs, record
it in the manifest; do not replace the interval or extend it selectively. Incomplete
prospective data means no final confirmation, not permission to use a favorable
retrospective subgroup.

## Fixed data contract

The universe is XAUUSD M5/M15/H1, EURUSD M5/M15, GBPUSD M5/M15, and US30 M5/M15.
The sole permitted source is locally obtained MT5 bar history containing UTC timestamp,
OHLC, symbol, timeframe, point size, and spread in points. No alternative feed, news
series, order-book series, manually edited candles, or cross-source replacement is
permitted for confirmatory analysis.

## Prior feature and interval contamination

`atr`, `atr_contraction_pct`, `compression_score`, and related ATR/range concepts were
previously inspected during Liquidity Sweep work. This family includes the explicitly
listed ATR-derived concepts solely because of its preregistered volatility mechanism;
prior Liquidity Sweep effects did not motivate their inclusion or parameter values and
cannot support this family. The entire known-used interval above remains contaminated
despite detector independence. Any result there is development or internal-validation
evidence only and can create at most a Candidate Discriminator Hypothesis. A confirmed
edge requires unchanged, post-activation independent prospective evidence.

The current fields with prior-inspection or conceptual-overlap status are
`atr_14_points`, `atr_56_points`, `atr_ratio_14_56`, `atr_ratio_change_8`,
`mean_range_8_points`, `mean_range_56_points`, and `range_ratio_8_56`. The first two
are ATR instances; the ratio/change and range fields are conceptually related to the
previously inspected contraction/compression concepts, but do not reuse their prior
values, segments, effects, or parameter selection. `efficiency_20` has no identified
prior Liquidity Sweep feature counterpart. This mapping is a contamination disclosure,
not evidence that any field is promising or reusable.
