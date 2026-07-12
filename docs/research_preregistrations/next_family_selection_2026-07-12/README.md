# Next research-family selection report - 2026-07-12

## Purpose and boundary

This package selects a possible next research family before any execution, backtest,
market-data access, or candidate-performance review. It is a methodological decision,
not a trading rule, detector implementation, edge claim, or profitability claim.

The closed Liquidity Sweep family is not a source of tuning, rescue, thresholds, or
selective interpretation for this package. The four conceptual candidates evaluated
are Volatility Regime Transition, Trend Continuation After Pullback, Session
Transition, and Abnormal Range Mean Reversion.

## Candidate profiles

### Volatility Regime Transition

- **Proposed mechanism:** a transition from comparatively compressed to expanding
  realized volatility may change the distribution of subsequent movement.
- **Falsifiable when:** a fixed, pre-decision transition detector fails its fixed
  support, stability, and cost-aware temporal gates.
- **Required data:** timestamped OHLC and spread in MT5 point units for the fixed
  symbol/timeframe universe; no order-book or external news data.
- **Pre-decision feasibility:** high; ATR, completed-bar ranges, and completed-bar
  close relationships can be computed at a completed-bar decision timestamp.
- **Conceptual frequency and cost sensitivity:** medium frequency; higher-volatility
  transitions can be sensitive to spread and slippage, so both are mandatory outcomes
  inputs rather than discovery features.
- **Degrees of freedom and auditability:** moderate but constrained by a fixed
  lookback set, one transition definition, one universe, and a feature registry.
- **Closure/post-hoc risk:** low overlap with Liquidity Sweep because it uses no sweep
  detection or reclaim fields; medium retrospective-selection risk if regimes or
  parameters were changed after results.
- **Principal weakness:** a volatility transition can be descriptive rather than
  directionally predictive.

### Trend Continuation After Pullback

- **Proposed mechanism:** a pause inside an established directional move may resume
  that move after a completed-bar pullback.
- **Falsifiable when:** its predeclared directional context and pullback detector fail
  fixed cost-aware temporal gates.
- **Required data:** OHLC and spread; no external data is intrinsically required.
- **Pre-decision feasibility:** feasible only with careful completed-bar definitions.
- **Conceptual frequency and cost sensitivity:** medium-to-high frequency; moderate
  spread/slippage sensitivity because continuation entries can occur after movement.
- **Degrees of freedom and auditability:** comparatively high: trend, pullback,
  resumption, and direction each invite competing definitions.
- **Closure/post-hoc risk:** low direct overlap with Liquidity Sweep but substantial
  risk of tuning pullback depth or trend context after results.
- **Principal weakness:** the conceptual mechanism is broad enough to conceal many
  distinct hypotheses.

### Session Transition

- **Proposed mechanism:** changes in participation around predefined session
  boundaries may alter short-horizon movement and execution conditions.
- **Falsifiable when:** a fixed UTC session-boundary detector fails fixed temporal
  gates under the declared spread/slippage contract.
- **Required data:** OHLC, spread, and reliable UTC timestamps; session calendar
  metadata is needed for auditability.
- **Pre-decision feasibility:** high for timestamp and completed-bar features.
- **Conceptual frequency and cost sensitivity:** frequent, but frequently exposed to
  changing spreads and liquidity at transitions.
- **Degrees of freedom and auditability:** moderate-to-high because session windows,
  daylight-saving conventions, and instrument-specific participation differ.
- **Closure/post-hoc risk:** low direct overlap with Liquidity Sweep; elevated risk of
  selecting favorable windows retrospectively.
- **Principal weakness:** UTC clock time can proxy unmeasured market events rather
  than a stable mechanism.

### Abnormal Range Mean Reversion

- **Proposed mechanism:** an unusually large completed-bar range may be followed by
  partial short-horizon reversal.
- **Falsifiable when:** a fixed abnormal-range definition and fixed reversal outcome
  fail the declared support, stability, cost, and temporal gates.
- **Required data:** OHLC and spread.
- **Pre-decision feasibility:** high when the range is from a completed bar.
- **Conceptual frequency and cost sensitivity:** medium frequency; potentially high
  cost sensitivity because abnormal ranges can coincide with adverse execution.
- **Degrees of freedom and auditability:** high: abnormality baseline, reversal
  horizon, and threshold definitions are all discretionary if not frozen.
- **Closure/post-hoc risk:** low direct overlap with Liquidity Sweep but high risk of
  post-hoc threshold rescue and favorable-event selection.
- **Principal weakness:** extreme ranges may represent information arrival, for which
  mean reversion is not a stable default.

## Decision

The fixed rubric, scorecard, and decision record select **Volatility Regime
Transition** with 27/30, four points above the next-ranked family. This is a
methodologically meaningful difference driven by strict observability, lower
interpretive ambiguity, and auditability, not by historical performance. The family
is only a preregistered proposal until this package is reviewed and merged.

See [the rubric](scoring_rubric.md), [completed scorecard](candidate_scorecard.md),
[decision record](selection_decision.md), and [full preregistration](preregistration_volatility_regime_transition.md).
