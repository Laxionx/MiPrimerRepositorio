# Edge V3/V4 methodology status

Historical journals generated before the price-unit contract are contaminated by malformed simulated entries: raw MT5 spread points were applied as price displacement. Edge V3 statistical conclusions and Edge V4 causal/economic conclusions are invalid pending a complete rerun using corrected research infrastructure.

The corrected post-price-unit trade population and Edge V4 audit remain valid. The corrected Edge V3 17-feature rerun is nevertheless invalid for strict interpretation: seven fields were treated as pre-trade even though their values depend on the effective next-bar entry.

For Edge V3 strict discovery, only features available at the completed setup-bar decision timestamp may be predictors. At-entry execution fields are not equivalent to pre-decision predictors: effective-entry risk/reward distances and their derivatives depend on the next entry bar, `spread_price`, and `slippage_price`, so they are classified `at_entry` and excluded. The next valid strict rerun must analyze only the ten verified numerical pre-decision predictors. `lower_quartile_closes` remains permanently excluded.

The Liquidity Sweep family remained frozen pending a corrected strict rerun. No Edge
V3 feature conclusion from the invalid 17-feature run may modify strategy. No
thresholding, feature interactions, ML, Candidate Rule Report, or operational change
was justified.

## Final strict rerun and closure — 2026-07-12

PR #26 merged the strict pre-decision provenance contract. The final rerun used the
canonical merge commit `5a8c2f51fe0294a742ec04460338eddbe7d9f493`, nine fixed MT5
symbol/timeframe runs, and the fixed UTC range `2026-01-01T00:00:00Z` through
`2026-07-10T21:00:00Z`. It analyzed exactly ten verified pre-decision predictors with
a deterministic 584/584 temporal split.

All ten predictors were rejected because none survived every mandatory gate; each
failed the temporal `non_negative` requirement. No Candidate Discriminator Hypothesis
and no Candidate Rule Report were created. The Liquidity Sweep family is therefore
**CLOSED**. An edge remains unconfirmed and the strategy is not confirmed profitable.
The next research family has not been selected.

The durable closure package and its evidence manifest are in
`docs/research_closures/liquidity_sweep_2026-07-12/`. The large raw history and
journals remain outside Git in the referenced durable archive. They are retained for
auditability only, not for tuning or rescue analysis of this closed family.

## Next-family selection and preregistration - 2026-07-12

Liquidity Sweep remains **CLOSED**; edge remains unconfirmed and profitable strategy remains unconfirmed.
Candidate-family selection has begun through an ex-ante methodological rubric. The provisional selection is Volatility Regime Transition, documented under
`docs/research_preregistrations/next_family_selection_2026-07-12/`.

No backtest, execution, MT5 connection, market-data generation, or order API call has
occurred for that prospective family. It is not an active research family until its
preregistration has been reviewed and merged; even then, its first execution remains
subject to the preregistration's separate implementation and prospective-validation
gates.

Volatility Regime Transition is selected, implemented, and still inactive. The
preregistration merge is `c635df3000c04c016801557e3427fb2e01a847c5`; the canonical
implementation merge is `807f79208c50043a8847f6d33f90e0c88076492d`; and the reviewed
implementation head is `e068ec01b52a21c92cb349189e0c0135c364453f`. A prepared,
machine-readable activation package freezes the future execution boundary, but its
prospective activation UTC timestamp remains null. Merging that package does not start
prospective validation. No MT5 or real-data execution, backtest, performance inspection,
or order API call has occurred. Liquidity Sweep remains formally closed; no edge and no
profitable strategy are confirmed.
