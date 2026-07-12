# Trade invariant summary

This summary is derived from the newly generated journals, paginated manifests, and
the existing Edge V4 descriptive audit. It is diagnostic-only.

| Check | Result |
| --- | --- |
| Opened trades with valid recorded LONG/SHORT geometry | 1,168 / 1,168 |
| Opened trades with invalid post-cost geometry | 0 |
| Take-profit exits with positive R | 364 / 364 |
| Stop-loss exits with negative R | 804 / 804 |
| PnL, R, and outcome label reconciliation | 1,168 / 1,168 |
| Canonical trade-ID collisions | 0 |
| Trade IDs containing timeframe | 1,168 / 1,168 |
| `spread_price == spread_points * point_size` | 1,168 / 1,168 |
| `slippage_price == slippage_points * point_size` | 1,168 / 1,168 |
| `r_multiple == pnl / risk` | 1,168 / 1,168 |

`point_size` and `tick_size` were retained as separate metadata fields. Their values
happened to be equal for these symbols, but spread and slippage normalization used
`point_size`, not `tick_size`.

The Edge V4 audit marked 33 complete records as ambiguous for intrabar TP/SL order
and 6 records as `data_unavailable` because their trade window crossed a detected
history gap. It did not infer intrabar ordering or fill gaps.
