# Funnel reconciliation

## Finding

The apparent `12,629` total is a presentation ambiguity, not a counting defect.
The `accepted_without_opening` counter is an intermediate journal state. It overlaps
with the one post-cost geometry rejection and must not be added as a terminal bucket.

## Evidence

Journal totals across the nine runs are:

| Counter | Value | Semantics |
| --- | ---: | --- |
| `journal_setups_generated` | 12,628 | Evaluable setups emitted by the runner. |
| `journal_setups_blocked` | 11,459 | Terminal gate blocks. |
| `journal_setups_accepted` | 1,169 | Passed initial gates; intermediate state. |
| `post_cost_geometry_blocks` | 1 | Accepted setup subsequently rejected after effective-entry cost geometry validation. |
| `trades_opened` | 1,168 | Terminal opened-trade count. |

Therefore, the exclusive terminal reconciliation is:

```text
11,459 gate blocks
     1 post-cost geometry block
 1,168 opened trades
------
12,628 evaluable setups
```

## Identified overlap

The sole post-cost block is in `run_005_eurusd_m15`:

- setup timestamp: `2026-03-27T22:45:00+00:00`
- attempted entry timestamp: `2026-03-30T00:00:00+00:00`
- symbol/timeframe/direction: `EURUSD` / `M15` / `LONG`
- reason: `invalid_post_cost_trade_geometry`
- effective entry: `1.15011`; stop loss: `1.150266`; take profit: `1.151598`

The setup journal records that setup as `accepted: true`; it has no trade record.
The post-cost block journal records the same setup timestamp. Thus the difference
between 1,169 initially accepted setups and 1,168 opened trades is exactly this one
post-cost rejection.

No source-code or report-generation change is required for the closure: the
documentation labels the counter as intermediate/overlapping.
