# Fixed candidate-family scoring rubric

## Lock

This rubric was defined before candidate scoring. It has ten equally weighted
criteria; each is scored as an integer from 0 through 3, for a maximum of 30. No
criterion, weight, candidate, or score may be changed after this document's scoring
table is applied. A future change requires a separately versioned selection process.

| Score | Fixed meaning |
|---|---|
| 0 | Fails the criterion, is unobservable, or cannot be audited without material unbounded discretion. |
| 1 | Weak: plausible only with major qualifications, high uncertainty, or a substantial methodological vulnerability. |
| 2 | Adequate: a defensible basis exists, but a meaningful limitation remains and must be controlled. |
| 3 | Strong: directly supports a constrained, auditable, ex-ante research design with no material unresolved limitation for that criterion. |

| Criterion | What is scored |
|---|---|
| 1. Independence | Separation from Liquidity Sweep concepts, fields, detector logic, and rescue evidence. |
| 2. Mechanism plausibility | Coherent market mechanism stated without relying on observed profitability. |
| 3. Pre-decision observability | Ability to define every discovery feature at the completed-bar decision timestamp. |
| 4. Existing MT5 data | Availability of required OHLC, spread, and timestamps in the already configured data source. |
| 5. Sample support | Conceptual ability to produce enough setups across the fixed universe without searching for favorable subgroups. |
| 6. Transaction-cost plausibility | Whether a cost-aware outcome can remain methodologically meaningful under spread and slippage. |
| 7. Low discretion | Few independently tunable detector, feature, or outcome choices. |
| 8. Falsifiability | A clear predeclared way for the family to fail. |
| 9. Auditability | Straightforward provenance, deterministic replay, and reviewability. |
| 10. Low retrospective risk | Resistance to selective windows, parameter rescue, and reinterpretation after results. |

The maximum total does not itself create an edge claim. A winner must lead the next
score by at least three points and have no score of 0 in criteria 1, 3, 8, or 9. If
either condition fails, selection is unresolved.
