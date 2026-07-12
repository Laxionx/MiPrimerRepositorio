# VRT activation-boundary TDD evidence

Source: the controlled-activation brief derived the inactive-package journeys; no market data or execution workflow was used.

| Guarantee | Test | Evidence |
| --- | --- | --- |
| Prepared record is deterministic and inactive | `test_valid_prepared_activation_package_is_inactive_and_deterministic` | Initial RED: missing `vrt_activation`; GREEN: focused activation suite passes. |
| Commit, file hash, detector, predictor, provenance, outcome, and unsafe-flag drift fail closed | `test_record_commit_and_hash_mismatches_fail_closed`, `test_detector_predictor_and_outcome_config_mismatches_fail_closed`, `test_unexpected_execution_flag_fails_closed` | Synthetic JSON mutations only. |
| A null prospective timestamp is permitted only while prepared | `test_prepared_record_allows_null_prospective_timestamp_but_rejects_activation` | No execution path is present. |
| Timestamps cannot activate before or at the record commit | `test_activation_timestamp_before_or_at_commit_fails_closed` | Synthetic timestamps only. |
| The observation schema is deterministic and unpopulated | `test_first_observation_schema_is_deterministic_and_unpopulated` | Template rejects observation permission and populated fields. |

Coverage is verified by the focused activation test command. The package deliberately has no live-data, MT5, backtest, order, performance, or prospective-activation path.
