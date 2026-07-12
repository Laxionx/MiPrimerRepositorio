# Canonical detector semantics

This document is the normative event-generator specification for
`volatility-regime-transition-vrt-20260712-v1`. It generates its population directly
from the declared volatility mechanism and never consumes, filters, joins, or ranks
Liquidity Sweep candidates, setups, trades, winners, losers, or cohorts. Timestamp
overlap with a Liquidity Sweep event may occur by chance, but the detector population
is independently generated. Liquidity Sweep remains formally closed and is not
reopened by this family.

## Inputs, units, and completed bars

For one `(symbol, timeframe)` stream, use only contiguous UTC MT5 bars with
`timestamp_utc`, bid `open_bid`, `high_bid`, `low_bid`, `close_bid`, `spread_points`, and
`point_size`. Prices and `point_size` are positive finite values; `high >= low`; and
`spread_points` is finite and non-negative. Calculations use unrounded IEEE-754
binary64 values. `tick_size` is audit metadata only and is never substituted for
`point_size`.

Bar `t` is eligible only when fully completed: its close time is no later than the
decision timestamp and no subsequent partially forming bar is used. A gap exists when
the difference between consecutive UTC bar-open timestamps exceeds three nominal
timeframe durations. A gap, invalid input, missing value, duplicate timestamp, or
non-monotonic timestamp resets this stream to `unavailable`; no state or rolling value
crosses that boundary.

## Volatility calculation and state machine

Within each contiguous valid segment, let
`TR_t = max(high_bid_t-low_bid_t, abs(high_bid_t-close_bid_(t-1)),
abs(low_bid_t-close_bid_(t-1)))` in price
units. For period `n`, initial `ATR_n` is the arithmetic mean of the first `n` true
ranges; thereafter `ATR_n(t) = ((n-1)*ATR_n(t-1)+TR_t)/n`. Define
`ratio_t = ATR_14(t)/ATR_56(t)`. A non-finite or non-positive denominator is
`unavailable`, not zero.

The warm-up is 64 valid, contiguous completed bars after every reset. Before warm-up,
the state is `unavailable`. At the first eligible decision bar, initialize state to
`below` when `ratio_t < 1.20`, otherwise `above`; initialization creates no event.

| State | Entry condition | Exit/reset condition |
|---|---|---|
| `below` | initialized when `ratio_t < 1.20`, or re-armed after an eligible bar with `ratio_t < 1.20` | a transition event when `ratio_t >= 1.20` and prior state is `below` |
| `above` | initialized when `ratio_t >= 1.20`, or entered by a transition event | first subsequent eligible bar with `ratio_t < 1.20`, which resets it to `below` and re-arms detection |
| `unavailable` | invalid/missing/gapped stream or insufficient warm-up | only 64 new valid contiguous completed bars may initialize it |

The threshold is exactly `1.20` and dimensionless. Equality belongs to `above`; only
strictly less than `1.20` is `below`. The transition starts and is confirmed on the
same completed decision bar: prior state must be `below` and `ratio_t >= 1.20`. There
is no additional persistence bar, no additional cooldown, and no configurable
alternative. This single-bar confirmation is the fixed persistence requirement. One
upward transition emits exactly one detector event, and no further event may emit
until a later eligible completed bar satisfies `ratio_t < 1.20` and re-arms the stream.

## Decision, direction, and event stream

The decision timestamp is the UTC close timestamp of decision bar `t`. The direction
is `long` only when `close_bid_t > close_bid_(t-8)` and `short` only when
`close_bid_t < close_bid_(t-8)`; equality produces a raw transition event with
direction `none` and terminal outcome `no_direction`, never a measurement. The
comparison requires both closes in the same contiguous segment. Direction is evaluated
only after the transition condition succeeds; it does not alter the volatility state
machine.

Each detector event has canonical preimage
`family_id|preregistration_version|symbol|timeframe|decision_timestamp_utc|below_to_above|direction|atr14=14|atr56=56|threshold=1.20|warmup=64`.
Its event ID is the lowercase SHA-256 of the UTF-8 preimage. A duplicate canonical ID
is a duplicate event and only the first occurrence in ascending source-row order is
retained; later duplicates are recorded as `duplicate_event` exclusions. Events are
ordered by `(decision_timestamp_utc, symbol, timeframe, event_id)`.

Each symbol/timeframe state machine is isolated. Session boundaries have no special
reset or permission; only the UTC continuity and validity rules above apply. The raw
ordered event stream retains every eligible upward transition. The separate outcome
policy may mark a raw event `suppressed_overlap` when an earlier event on the same
symbol/timeframe still has an active outcome; suppression never changes or deletes the
detector event stream.
