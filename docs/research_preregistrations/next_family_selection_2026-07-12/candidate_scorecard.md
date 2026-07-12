# Completed candidate scorecard

All scores use the locked equal-weight rubric in [scoring_rubric.md](scoring_rubric.md).
They reflect ex-ante methodological properties only; no historical results were
examined or used.

| Criterion | Volatility Regime Transition | Trend Continuation After Pullback | Session Transition | Abnormal Range Mean Reversion |
|---|---:|---:|---:|---:|
| 1. Independence | 3 | 3 | 3 | 3 |
| 2. Mechanism plausibility | 3 | 2 | 2 | 2 |
| 3. Pre-decision observability | 3 | 3 | 3 | 3 |
| 4. Existing MT5 data | 3 | 3 | 3 | 3 |
| 5. Sample support | 3 | 3 | 2 | 2 |
| 6. Transaction-cost plausibility | 2 | 2 | 2 | 1 |
| 7. Low discretion | 2 | 1 | 1 | 1 |
| 8. Falsifiability | 3 | 3 | 3 | 3 |
| 9. Auditability | 3 | 2 | 2 | 2 |
| 10. Low retrospective risk | 2 | 1 | 1 | 1 |
| **Total** | **27** | **23** | **22** | **21** |

## Justifications and major risks

| Family | Written justification | Major risk |
|---|---|---|
| Volatility Regime Transition | Completed-bar volatility inputs, a single transition event, and transparent cost-aware outcomes give the clearest constrained path. It is entirely separate from sweep/reclaim logic. | The transition may alter variability without producing directional predictability. |
| Trend Continuation After Pullback | Data and completed-bar observability are good, but trend and pullback definitions create several plausible competing specifications. | Post-result selection among trend, pullback, and resumption definitions. |
| Session Transition | UTC timestamps make basic observability good, but calendar/window choice and changing market participation increase interpretation risk. | Favorable-session selection and session convention drift. |
| Abnormal Range Mean Reversion | The event is observable and falsifiable, but abnormality and reversal specifications have high threshold discretion and execution may be adverse. | Threshold rescue after event outcomes are known. |

## Ranking and outcome

1. Volatility Regime Transition - 27
2. Trend Continuation After Pullback - 23
3. Session Transition - 22
4. Abnormal Range Mean Reversion - 21

Volatility Regime Transition exceeds the next score by four points and has no
disqualifying score of 0. Under the predeclared selection rule it is selected for
preregistration. The score is not evidence of edge or profitability.
