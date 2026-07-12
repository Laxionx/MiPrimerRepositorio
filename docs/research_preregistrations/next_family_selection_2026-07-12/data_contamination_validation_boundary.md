# Data-contamination and validation boundary

## Known-used interval

`2026-01-01T00:00:00Z` through `2026-07-10T21:00:00Z` has already been used
extensively by the laboratory. It is not pristine independent validation for
Volatility Regime Transition and must never be described as such.

| Role | Fixed interval or policy | Allowed conclusion |
|---|---|---|
| Development | `2026-01-01T00:00:00Z` to `2026-04-30T23:59:59Z` | Specification/debug evidence only; no edge or profitability claim. |
| Internal temporal validation | `2026-05-01T00:00:00Z` to `2026-07-10T21:00:00Z` | Candidate-hypothesis evidence only after all gates; no edge or profitability claim. |
| Prospective independent validation | Begins `00:00:00Z` on the first day of the first full calendar month after preregistration merge; ends after three complete calendar months. | Required, unchanged independent replication before any final edge or profitability claim. |

The prospective period must be accumulated after the merge without detector, universe,
feature, cost, split, gate, or outcome-policy changes. If a material market-data gap
occurs, record it in the manifest; do not replace the interval or extend it selectively.
Incomplete prospective data means no final confirmation, not permission to use a
favorable retrospective subgroup.

## Fixed data contract

The universe is XAUUSD M5/M15/H1, EURUSD M5/M15, GBPUSD M5/M15, and US30 M5/M15.
The sole permitted source is locally obtained MT5 bar history containing UTC timestamp,
OHLC, symbol, timeframe, point size, and spread in points. No alternative feed, news
series, order-book series, manually edited candles, or cross-source replacement is
permitted for confirmatory analysis.
