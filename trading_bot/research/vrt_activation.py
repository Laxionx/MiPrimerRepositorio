"""Fail-closed validation for the inactive VRT activation package."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from trading_bot.research import volatility_regime_transition as vrt


PREREGISTRATION_COMMIT = "c635df3000c04c016801557e3427fb2e01a847c5"
IMPLEMENTATION_MERGE_COMMIT = "807f79208c50043a8847f6d33f90e0c88076492d"
REVIEWED_IMPLEMENTATION_HEAD = "e068ec01b52a21c92cb349189e0c0135c364453f"
ACTIVATION_RECORD_CREATION_COMMIT = "91342b3a6b5957ad6f5d041c4b466ac866f00400"
ACTIVATION_RECORD_CREATION_UTC = "2026-07-12T22:59:37Z"
ACTIVATION_EXECUTION_COMMIT = "aad92d3a20c07e955cd69aa9bacc8d1e9784365d"
ACTIVATION_EXECUTION_COMMIT_UTC = "2026-07-12T23:27:35Z"
FAMILY_ID = "volatility-regime-transition-vrt-20260712-v1"
PACKAGE_RELATIVE = Path("docs/research_preregistrations/next_family_selection_2026-07-12")
MANIFEST_NAME = "preregistration_manifest.json"
PROVENANCE_NAME = "feature_provenance_plan.md"
CONFIG_NAME = "vrt_frozen_execution_configuration.json"
RECORD_NAME = "vrt_activation_record.json"
OBSERVATION_SCHEMA_NAME = "vrt_first_observation_record.schema.json"
IMPLEMENTATION_RELATIVE = Path("trading_bot/research/volatility_regime_transition.py")
EXECUTION_FLAGS = (
    "mt5_connected", "real_data_observed", "backtest_executed",
    "performance_inspected", "prospective_validation_started", "order_api_called",
)
OBSERVATION_REQUIRED = (
    "family_id", "family_version", "activation_record_sha256", "activation_record_commit",
    "prospective_activation_at_utc", "input_data_artifact_hashes", "execution_command",
    "execution_configuration_sha256", "implementation_commit", "preregistration_commit",
    "provenance_sha256", "output_directory", "expected_report_schemas",
    "observation_started_at_utc", "observation_completed_at_utc", "immutable_run_id",
    "results_not_inspected_before_record_written",
)
POSITION_OVERLAP_POLICY = "one_active_outcome_per_symbol_timeframe_until_first_exit_or_bar_48; later_raw_events_suppressed_overlap"
SCORECARD_POLICY = "every_support_stability_temporal_cost_and_multiplicity_gate_must_pass"
CANDIDATE_HYPOTHESIS_POLICY = "only_a_fully_passing_retrospective_scorecard_may_create_a_candidate_discriminator_hypothesis_never_a_trading_rule"


class ActivationConformanceError(ValueError):
    """Raised whenever the inactive activation boundary is not exact."""


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ActivationConformanceError(f"missing required file: {path}") from exc


def _load_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActivationConformanceError(f"invalid or missing JSON: {path}") from exc
    if not isinstance(parsed, dict):
        raise ActivationConformanceError(f"JSON object required: {path}")
    return parsed


def _expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ActivationConformanceError(f"{label} mismatch")


def _utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ActivationConformanceError(f"{label} must be an UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ActivationConformanceError(f"{label} must be an UTC timestamp") from exc
    if parsed.tzinfo is None:
        raise ActivationConformanceError(f"{label} must include an UTC offset")
    return parsed.astimezone(UTC)


def _detector_contract(manifest: Mapping[str, Any]) -> dict[str, Any]:
    detector = manifest.get("detector")
    if not isinstance(detector, dict):
        raise ActivationConformanceError("detector contract is missing")
    return detector


def _validate_execution_config(manifest: Mapping[str, Any], manifest_path: Path, config: Mapping[str, Any]) -> None:
    _expect(config.get("schema_version"), "vrt_frozen_execution_configuration.v1", "execution config schema")
    _expect(config.get("family_id"), FAMILY_ID, "execution config family")
    _expect(config.get("family_version"), manifest.get("preregistration_version"), "execution config family version")
    _expect(config.get("preregistration_manifest_path"), str(PACKAGE_RELATIVE / MANIFEST_NAME).replace("\\", "/"), "execution config manifest path")
    _expect(config.get("preregistration_manifest_sha256"), _sha256_file(manifest_path), "execution config manifest hash")
    _expect(config.get("symbols_timeframes"), manifest.get("universe"), "symbol/timeframe")
    _expect(config.get("temporal_split"), manifest.get("periods"), "temporal split")
    _expect(config.get("detector"), _detector_contract(manifest), "detector")
    registry = manifest.get("feature_registry")
    if not isinstance(registry, dict):
        raise ActivationConformanceError("feature provenance is missing")
    strict = config.get("strict_predictors")
    if not isinstance(strict, dict):
        raise ActivationConformanceError("strict predictor configuration is missing")
    _expect(strict.get("names"), registry.get("discovery_matrix"), "strict predictor")
    _expect(strict.get("common_missing_policy"), registry.get("common_missing_policy"), "missing-value policy")
    _expect(strict.get("gap_behavior"), registry.get("gap_behavior"), "gap handling")
    _expect(strict.get("outcome_only_excluded"), registry.get("outcome_only_excluded"), "provenance exclusion")
    _expect(config.get("outcome_contract"), manifest.get("outcome_contract"), "outcome contract")
    _expect(config.get("gates"), manifest.get("gates"), "gates")
    _expect(config.get("closure_policy"), manifest.get("closure_policy"), "closure policy")
    _expect(config.get("position_overlap_policy"), POSITION_OVERLAP_POLICY, "position-overlap policy")
    _expect(config.get("scorecard_policy"), SCORECARD_POLICY, "scorecard policy")
    _expect(config.get("candidate_hypothesis_policy"), CANDIDATE_HYPOTHESIS_POLICY, "candidate-hypothesis policy")
    _expect(config.get("execution_authorized"), False, "execution authorization")
    if config.get("completed_bar_policy") != "completed_bar_t_only; no_partial_or_future_bar_dependency":
        raise ActivationConformanceError("completed-bar policy mismatch")
    if config.get("point_size_tick_size_policy") != "spread_points_times_point_size; tick_size_substitution_forbidden":
        raise ActivationConformanceError("point-size contract mismatch")


def validate_first_observation_schema(schema: Mapping[str, Any]) -> None:
    _expect(schema.get("schema_version"), "vrt_first_observation_record.v1", "first-observation schema")
    _expect(tuple(schema.get("required_fields", ())), OBSERVATION_REQUIRED, "first-observation required fields")
    _expect(schema.get("status"), "template_not_observed", "first-observation status")
    _expect(schema.get("observation_permitted_by_this_template"), False, "first-observation permission")
    _expect(schema.get("real_data_observed"), False, "first-observation data flag")
    _expect(schema.get("performance_inspected"), False, "first-observation performance flag")
    template = schema.get("record_template")
    if not isinstance(template, dict) or set(template) != set(OBSERVATION_REQUIRED) or any(value is not None for value in template.values()):
        raise ActivationConformanceError("first-observation template must be unpopulated")


def validate_activation_package(
    root: str | Path,
    *,
    execution_config_path: str | Path | None = None,
    activation_record_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate files independently; this function never activates or executes VRT."""
    repo = Path(root)
    package = repo / PACKAGE_RELATIVE
    manifest_path = package / MANIFEST_NAME
    provenance_path = package / PROVENANCE_NAME
    implementation_path = repo / IMPLEMENTATION_RELATIVE
    config_path = Path(execution_config_path) if execution_config_path is not None else package / CONFIG_NAME
    record_path = Path(activation_record_path) if activation_record_path is not None else package / RECORD_NAME
    observation_path = package / OBSERVATION_SCHEMA_NAME
    manifest = _load_json(manifest_path)
    config = _load_json(config_path)
    record = _load_json(record_path)
    _load_json(observation_path)
    if not provenance_path.is_file() or not implementation_path.is_file():
        raise ActivationConformanceError("missing required provenance or detector implementation")
    try:
        implementation_conformance = vrt.validate_preregistration_conformance(manifest_path)
    except (vrt.ManifestConformanceError, vrt.ProvenanceContractError) as exc:
        raise ActivationConformanceError("implemented detector/provenance mismatch") from exc
    _expect(manifest.get("preregistration_version"), FAMILY_ID, "preregistration family")
    _expect(manifest.get("execution_authorized_by_this_manifest"), False, "manifest execution authorization")
    _validate_execution_config(manifest, manifest_path, config)
    _expect(record.get("schema_version"), "vrt_activation_record.v1", "activation record schema")
    _expect(record.get("family_id"), FAMILY_ID, "activation record family")
    _expect(record.get("family_version"), FAMILY_ID, "activation record family version")
    _expect(record.get("preregistration_merge_commit"), PREREGISTRATION_COMMIT, "preregistration commit")
    _expect(record.get("implementation_merge_commit"), IMPLEMENTATION_MERGE_COMMIT, "implementation commit")
    _expect(record.get("reviewed_implementation_head"), REVIEWED_IMPLEMENTATION_HEAD, "reviewed implementation head")
    _expect(record.get("activation_record_commit"), ACTIVATION_RECORD_CREATION_COMMIT, "activation record commit")
    _expect(record.get("committed_at_utc"), ACTIVATION_RECORD_CREATION_UTC, "activation record committed timestamp")
    _expect(record.get("preregistration_manifest_path"), str(PACKAGE_RELATIVE / MANIFEST_NAME).replace("\\", "/"), "preregistration manifest path")
    _expect(record.get("feature_provenance_path"), str(PACKAGE_RELATIVE / PROVENANCE_NAME).replace("\\", "/"), "feature provenance path")
    _expect(record.get("detector_implementation_path"), str(IMPLEMENTATION_RELATIVE).replace("\\", "/"), "detector implementation path")
    _expect(record.get("frozen_execution_configuration_path"), str(PACKAGE_RELATIVE / CONFIG_NAME).replace("\\", "/"), "execution configuration path")
    _expect(record.get("preregistration_manifest_sha256"), _sha256_file(manifest_path), "preregistration manifest hash")
    _expect(record.get("feature_provenance_sha256"), _sha256_file(provenance_path), "provenance hash")
    _expect(record.get("detector_implementation_sha256"), _sha256_file(implementation_path), "detector implementation hash")
    _expect(record.get("frozen_execution_configuration_sha256"), _sha256_file(config_path), "execution configuration hash")
    _expect(record.get("symbols_timeframes"), manifest.get("universe"), "activation symbols/timeframes")
    _expect(record.get("fixed_periods"), manifest.get("periods"), "activation temporal split")
    status = record.get("status")
    if status not in {"prepared_not_activated", "activation_requirements_complete", "active_prospective"}:
        raise ActivationConformanceError("activation status mismatch")
    for flag in EXECUTION_FLAGS:
        _expect(record.get(flag), False, flag)
    _utc(record.get("prepared_at_utc"), "prepared timestamp")
    prospective = record.get("prospective_activation_at_utc")
    if prospective is not None:
        if status == "active_prospective":
            _expect(record.get("activation_commit"), ACTIVATION_EXECUTION_COMMIT, "activation commit")
            _expect(record.get("activation_committed_at_utc"), ACTIVATION_EXECUTION_COMMIT_UTC, "activation commit timestamp")
            if _utc(prospective, "activation timestamp") <= _utc(record["activation_committed_at_utc"], "activation commit timestamp"):
                raise ActivationConformanceError("activation timestamp must follow activation commit")
            return {
                "status": status, "prospective_activation_at_utc": prospective,
                "activation_record_sha256": canonical_json_sha256(record),
                "manifest_sha256": implementation_conformance["manifest_sha256"],
            }
        if status != "activation_requirements_complete":
            raise ActivationConformanceError("prospective activation is not permitted for a prepared record")
        committed = _utc(record.get("committed_at_utc"), "committed timestamp")
        activation = _utc(prospective, "activation timestamp")
        if activation <= committed:
            raise ActivationConformanceError("activation timestamp must follow activation-record commit")
        raise ActivationConformanceError("prospective activation requires a separate execution task")
    if status != "prepared_not_activated":
        raise ActivationConformanceError("null prospective activation requires prepared status")
    if record.get("committed_at_utc") is not None:
        _utc(record["committed_at_utc"], "committed timestamp")
    observation = _load_json(observation_path)
    validate_first_observation_schema(observation)
    return {
        "status": record["status"],
        "prospective_activation_at_utc": None,
        "activation_record_sha256": canonical_json_sha256(record),
        "manifest_sha256": implementation_conformance["manifest_sha256"],
    }
