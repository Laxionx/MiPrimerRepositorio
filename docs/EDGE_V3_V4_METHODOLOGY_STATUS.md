# Edge V3/V4 methodology status

Historical journals generated before the price-unit contract are contaminated by malformed simulated entries: raw MT5 spread points were applied as price displacement. Edge V3 statistical conclusions and Edge V4 causal/economic conclusions are invalid pending a complete rerun using corrected research infrastructure.

The corrected post-price-unit trade population and Edge V4 audit remain valid. The corrected Edge V3 17-feature rerun is nevertheless invalid for strict interpretation: seven fields were treated as pre-trade even though their values depend on the effective next-bar entry.

For Edge V3 strict discovery, only features available at the completed setup-bar decision timestamp may be predictors. At-entry execution fields are not equivalent to pre-decision predictors: effective-entry risk/reward distances and their derivatives depend on the next entry bar, `spread_price`, and `slippage_price`, so they are classified `at_entry` and excluded. The next valid strict rerun must analyze only the ten verified numerical pre-decision predictors. `lower_quartile_closes` remains permanently excluded.

The Liquidity Sweep family remains frozen, not formally rejected. No Edge V3 feature conclusion from the invalid 17-feature run may modify strategy. No thresholding, feature interactions, ML, Candidate Rule Report, or operational change is justified. Old generated journals and reports are retained only as audit evidence and must not be used as research evidence.
