# Volatility Regime Transition provenance contract

The decision timestamp is the close timestamp of completed bar `t`, as defined in
[detector semantics](detector_semantics.md). Every dependency is recursively confined
to the same contiguous valid segment at or before that timestamp. A missing,
non-finite, invalid, gapped, or excluded transitive dependency makes the dependent
field unavailable; unavailable fields are never imputed.

## Primitive input and audit fields

| Field | Role/type/nullable | Unit and invariant | Basis, timing, and missing/gap handling |
|---|---|---|---|
| `timestamp_utc` | detector input; UTC timestamp; false | strictly increasing bar-open timestamp | local MT5 bar; `pre_decision`; duplicate/non-monotonic/missing resets state. |
| `symbol` | detector input; string; false | one declared universe symbol | bar metadata; `pre_decision`; a stream is isolated by this field. |
| `timeframe` | detector input; enum; false | one declared universe timeframe | bar metadata; `pre_decision`; gap duration derives from this field. |
| `open_bid`, `high_bid`, `low_bid`, `close_bid` | detector input; float64; false | positive price; `high_bid >= low_bid` | completed MT5 bid OHLC; `pre_decision`; invalid value resets state. |
| `spread_points` | audit/outcome input; float64; false | non-negative broker points | completed MT5 bar; `at_entry` for next-bar measurement; never strict-eligible. |
| `point_size` | audit/outcome input; float64; false | positive price per point | symbol metadata; `at_entry` for costs; never strict-eligible. |
| `tick_size` | audit-only; float64; nullable | positive if supplied | symbol metadata; excluded because it must not replace `point_size` in spread conversion. |

## Derived detector and discovery fields

All fields below are `float64`, except `regime_state` and `direction`. Formulas use
unrounded binary64 values. A denominator that is non-positive/non-finite, or a source
outside the current contiguous segment, produces unavailable rather than zero.

| Field | Role / nullable / unit or invariant | Definition and `depends_on_fields` | Timing, bar use, and strict status |
|---|---|---|---|
| `true_range_points` | detector state; true; price | `max(high-low, abs(high-close_prev), abs(low-close_prev))`; depends on `high_bid`, `low_bid`, `close_bid`. | `pre_decision`; current high/low and prior completed close; detector-only, excluded from discovery matrix. |
| `atr_14_points` | detector input and discovery predictor; true; price | Wilder ATR(14) of `true_range_points`; depends on `true_range_points`. | `pre_decision`; current completed bar; strict-eligible. Previously inspected ATR-related concept; inclusion is mechanism-based only. |
| `atr_56_points` | detector input and discovery predictor; true; price | Wilder ATR(56) of `true_range_points`; depends on `true_range_points`. | `pre_decision`; current completed bar; strict-eligible. |
| `atr_ratio_14_56` | detector input and discovery predictor; true; dimensionless, positive | `atr_14_points/atr_56_points`; depends on both ATR fields. | `pre_decision`; current completed bar; strict-eligible. |
| `prior_atr_ratio_14_56` | detector state; true; dimensionless | immediately preceding completed `atr_ratio_14_56`; depends on `atr_ratio_14_56`. | `pre_decision`; prior bar only; detector-only, excluded to prevent duplicate representation. |
| `regime_state` | detector state; true; enum `unavailable|below|above` | canonical state machine; depends on `atr_ratio_14_56`, `prior_atr_ratio_14_56`, `timestamp_utc`. | `pre_decision`; current/prior completed bars; never a discovery predictor. |
| `atr_ratio_change_8` | discovery predictor; true; dimensionless | current ratio minus ratio eight completed bars earlier; depends on `atr_ratio_14_56`. | `pre_decision`; current and prior bars; strict-eligible. |
| `mean_range_8_points` | discovery predictor; true; price | mean `high_bid-low_bid` over `t-7..t`; depends on `high_bid`, `low_bid`. | `pre_decision`; completed bars only; strict-eligible. |
| `mean_range_56_points` | discovery predictor; true; price | mean `high_bid-low_bid` over `t-55..t`; depends on `high_bid`, `low_bid`. | `pre_decision`; completed bars only; strict-eligible. |
| `range_ratio_8_56` | discovery predictor; true; dimensionless | `mean_range_8_points/mean_range_56_points`; depends on both range means. | `pre_decision`; current completed bar; strict-eligible. |
| `efficiency_20` | discovery predictor; true; range `[0,1]` | `abs(close_t-close_t-20)/sum(abs(close_i-close_i-1), i=t-19..t)`; depends on `close_bid`. | `pre_decision`; completed bars only; strict-eligible. |
| `direction` | detector/output state; false; enum `long|short|none` | long if `close_t > close_t-8`, short if `<`, else none; depends on `close_bid`. | `pre_decision`; `none` is terminal `no_direction`; detector-only, excluded from discovery matrix. |

The discovery matrix is exactly `atr_14_points`, `atr_56_points`,
`atr_ratio_14_56`, `atr_ratio_change_8`, `mean_range_8_points`,
`mean_range_56_points`, `range_ratio_8_56`, and `efficiency_20`. No detector state,
raw input, or future implementation internal becomes a predictor unless this versioned
contract is amended before real-data execution.

## Outcome-only and excluded fields

`next_bar_open_bid`, `spread_price`, `slippage_price`, effective entry/exit, stop,
target, risk denominator, reward, PnL, R, MFE, MAE, terminal outcome, and future-bar
prices are outcome/audit-only. They are `at_entry` or later and therefore explicitly
ineligible for strict discovery. Liquidity Sweep fields (`sweep_depth`,
`reclaim_speed`, sweep occurrence, and all closed-family cohorts/results) are excluded
because of family independence, not merely timing.

The machine-readable `feature_registry` in `preregistration_manifest.json` is the
canonical serialization of this contract. A future implementation must emit direct and
transitive dependency evidence for every field and fail closed on any discrepancy.
