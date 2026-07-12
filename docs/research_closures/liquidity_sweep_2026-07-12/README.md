# Liquidity Sweep family closure — 2026-07-12

## Status

**Family:** Liquidity Sweep
**Final status:** **CLOSED**
**Closure reason:** No strict pre-decision discriminator survived every mandatory Edge V3 gate.

This is a methodological closure, not a strategy change. It does not create a
Candidate Rule Report, a trading rule, an edge claim, or a profitability claim.

## Canonical execution

- Canonical code commit: `5a8c2f51fe0294a742ec04460338eddbe7d9f493`
- Fixed UTC range: `2026-01-01T00:00:00Z` through `2026-07-10T21:00:00Z`
- MT5 history mode: paginated; page size: 5000; current forming bar excluded.
- Universe: XAUUSD M5, XAUUSD M15, XAUUSD H1, EURUSD M5, EURUSD M15,
  GBPUSD M5, GBPUSD M15, US30 M5, and US30 M15.
- Deterministic temporal split: 584 train observations and 584 test observations.

## Data and setup funnel

- 225,000 raw candles; 204,321 filtered candles.
- 12,794 detector candidates; 166 candidates suppressed while a position was open.
- 12,628 evaluable setups; 1,168 opened trades.
- Terminal categories reconcile as 11,459 gate blocks + 1 post-cost geometry block
  + 1,168 opened trades = 12,628 evaluable setups.

`accepted_without_opening=1` is an intermediate journal counter, not an additional
terminal outcome. It is the same EURUSD M15 setup later rejected by post-cost
geometry. See [FUNNEL_RECONCILIATION.md](FUNNEL_RECONCILIATION.md).

## Descriptive trade result

- 364 winners and 804 losers; win rate 31.1644%.
- Expectancy: -0.106706 R; payoff ratio: 1.866393; aggregate R: -124.632900.
- MFE/R: mean 1.347499, median 1.019463; MAE/R: mean 1.404469,
  median 1.211958, across 1,162 complete excursion records.

These are descriptive results only. They do not establish an edge or a profitable
strategy.

## Strict Edge V3 result

The strict matrix contained exactly these 10 pre-decision predictors:

`atr`, `atr_contraction_pct`, `average_pullback_depth`, `compression_score`,
`pressure_score`, `price_position_in_range`, `prior_range_points`,
`range_duration_bars`, `recent_range_points`, and `upper_quartile_closes`.

All 10 had strict provenance and sufficient scorecard sample support, but all failed
the mandatory temporal `non_negative` condition. Each was rejected for
`negative_test_performance`; none passed every gate.

The following stayed excluded: the seven effective-entry `at_entry` metrics;
`lower_quartile_closes`; outcomes; PnL and R fields; MFE/MAE; post-entry and
post-trade fields; and unknown-timing fields including `sweep_depth` and
`reclaim_speed`.

- Candidate Discriminator Hypotheses: none.
- Candidate Rule Report: not created.
- Confirmed edge: no.
- Confirmed profitable strategy: no.

Positive global effects and near-passes do not override a failed mandatory gate.

## Boundary after closure

The rejected results must not be reused to tune thresholds, instruments, timeframes,
gates, feature combinations, stop-loss, or take-profit behavior. Any future research
must start as a separately declared strategy family or hypothesis with its universe,
features, and evaluation policy fixed before results are examined. It must not be
presented as a rescue or continuation of this closed Liquidity Sweep family.

## Evidence

The immutable source evidence was copied from the temporary execution directory to:

`C:\Users\USER\Documents\Codex\ResearchEvidence\mt5-algorithmic-lab\liquidity-sweep-closure-20260712\evidence_original`

The committed [evidence manifest](evidence_manifest.json) records every original
artifact, size, SHA-256, role, original source path, durable destination, and copy
verification. Raw market CSVs and journals remain outside Git in that durable archive.
The archive also contains this lightweight closure package.

## Companion records

- [Funnel reconciliation](FUNNEL_RECONCILIATION.md)
- [Trade invariant summary](TRADE_INVARIANT_SUMMARY.md)
- [Commands executed](COMMANDS_EXECUTED.md)
- [Evidence manifest](evidence_manifest.json)
