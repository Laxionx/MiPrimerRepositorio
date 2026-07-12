# Volatility Regime Transition feature-provenance plan

Decision timestamp `t` is the close of a fully completed bar. Every discovery input
below may use only bars with close time at or before `t`; no next-bar price, effective
entry, spread, slippage, outcome, or post-entry field is a discovery feature.

| Field | Definition at `t` | Timing | `depends_on_fields` | Strict eligibility |
|---|---|---|---|---|
| `atr_14_points` | Wilder ATR over the 14 completed bars ending at `t`, in price points. | `pre_decision` | `high`, `low`, `close` | Eligible |
| `atr_56_points` | Wilder ATR over the 56 completed bars ending at `t`, in price points. | `pre_decision` | `high`, `low`, `close` | Eligible |
| `atr_ratio_14_56` | `atr_14_points / atr_56_points`; missing when denominator is non-positive. | `pre_decision` | `atr_14_points`, `atr_56_points` | Eligible |
| `atr_ratio_change_8` | Current `atr_ratio_14_56` minus its value eight completed bars earlier. | `pre_decision` | `atr_ratio_14_56` | Eligible |
| `mean_range_8_points` | Arithmetic mean of high-low over completed bars `t-7` through `t`. | `pre_decision` | `high`, `low` | Eligible |
| `mean_range_56_points` | Arithmetic mean of high-low over completed bars `t-55` through `t`. | `pre_decision` | `high`, `low` | Eligible |
| `range_ratio_8_56` | `mean_range_8_points / mean_range_56_points`; missing on a non-positive denominator. | `pre_decision` | `mean_range_8_points`, `mean_range_56_points` | Eligible |
| `efficiency_20` | `abs(close_t-close_t-20) / sum(abs(close_i-close_i-1), i=t-19..t)`; missing on zero denominator. | `pre_decision` | `close` | Eligible |

The detector is allowed to use only `atr_ratio_14_56` and its immediately preceding
completed-bar value. The remaining fields are predeclared descriptors; they cannot be
added to, removed from, combined into, or used to tune the detector after results.

Always-excluded fields include bid/ask or effective next-bar entry, `spread_price`,
`slippage_price`, risk/reward distances, stop/target outcomes, PnL, R, MFE, MAE,
future bars, and all Liquidity Sweep-specific fields such as `sweep_depth` and
`reclaim_speed`. A future implementation must emit this registry, direct/transitive
dependency evidence, timing, source basis, and eligibility status for every field.
