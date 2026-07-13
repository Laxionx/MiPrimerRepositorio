from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from trading_bot.research import vrt_activation


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/research_preregistrations/next_family_selection_2026-07-12"
CONFIG = PACKAGE / "vrt_frozen_execution_configuration.json"
RECORD = PACKAGE / "vrt_activation_record.json"
OBSERVATION = PACKAGE / "vrt_first_observation_record.schema.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _prepared_record(tmp_path: Path) -> Path:
    path = tmp_path / "activation.json"
    _write_json(path, _json(RECORD))
    return path


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    _write_json(path, _json(CONFIG))
    return path


def test_active_activation_package_is_deterministic():
    result = vrt_activation.validate_activation_package(ROOT)

    assert result["status"] == "active_prospective"
    assert result["activation_record_sha256"] == vrt_activation.canonical_json_sha256(_json(RECORD))
    assert result["prospective_activation_at_utc"] == "2026-07-12T23:59:38Z"


def test_missing_manifest_fails_closed(tmp_path):
    with pytest.raises(vrt_activation.ActivationConformanceError, match="missing"):
        vrt_activation.validate_activation_package(tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("preregistration_merge_commit", "0" * 40, "preregistration commit"),
        ("implementation_merge_commit", "0" * 40, "implementation commit"),
        ("preregistration_manifest_sha256", "0" * 64, "hash"),
        ("feature_provenance_sha256", "0" * 64, "provenance"),
    ],
)
def test_record_commit_and_hash_mismatches_fail_closed(tmp_path, field, value, error):
    record_path = _prepared_record(tmp_path)
    record = _json(record_path)
    record[field] = value
    _write_json(record_path, record)

    with pytest.raises(vrt_activation.ActivationConformanceError, match=error):
        vrt_activation.validate_activation_package(ROOT, activation_record_path=record_path)


def test_detector_predictor_and_outcome_config_mismatches_fail_closed(tmp_path):
    config_path = _config(tmp_path)
    config = _json(config_path)
    config["detector"]["threshold"]["value"] = 1.21
    _write_json(config_path, config)
    with pytest.raises(vrt_activation.ActivationConformanceError, match="detector"):
        vrt_activation.validate_activation_package(ROOT, execution_config_path=config_path)

    config = _json(CONFIG)
    config["strict_predictors"]["names"] = ["efficiency_20"]
    _write_json(config_path, config)
    with pytest.raises(vrt_activation.ActivationConformanceError, match="strict predictor"):
        vrt_activation.validate_activation_package(ROOT, execution_config_path=config_path)

    config = _json(CONFIG)
    config["outcome_contract"]["max_holding_bars"] = 47
    _write_json(config_path, config)
    with pytest.raises(vrt_activation.ActivationConformanceError, match="outcome"):
        vrt_activation.validate_activation_package(ROOT, execution_config_path=config_path)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("preregistration_manifest_sha256", "0" * 64, "execution config manifest hash"),
        ("position_overlap_policy", "allow_all_overlaps", "position-overlap policy"),
        ("scorecard_policy", "optional", "scorecard policy"),
        ("candidate_hypothesis_policy", "trade_rule", "candidate-hypothesis policy"),
    ],
)
def test_config_policy_drift_fails_even_when_record_hash_is_updated(tmp_path, field, value, error):
    config_path = _config(tmp_path)
    record_path = _prepared_record(tmp_path)
    config = _json(config_path)
    config[field] = value
    _write_json(config_path, config)
    record = _json(record_path)
    record["frozen_execution_configuration_sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
    _write_json(record_path, record)

    with pytest.raises(vrt_activation.ActivationConformanceError, match=error):
        vrt_activation.validate_activation_package(
            ROOT, execution_config_path=config_path, activation_record_path=record_path
        )


def test_unexpected_execution_flag_fails_closed(tmp_path):
    record_path = _prepared_record(tmp_path)
    record = _json(record_path)
    record["order_api_called"] = True
    _write_json(record_path, record)

    with pytest.raises(vrt_activation.ActivationConformanceError, match="order_api_called"):
        vrt_activation.validate_activation_package(ROOT, activation_record_path=record_path)


def test_prepared_record_allows_null_prospective_timestamp_but_rejects_activation(tmp_path):
    record_path = _prepared_record(tmp_path)
    record = _json(record_path)
    record["prospective_activation_at_utc"] = "2026-07-12T00:00:00Z"
    _write_json(record_path, record)

    with pytest.raises(vrt_activation.ActivationConformanceError, match="activation timestamp"):
        vrt_activation.validate_activation_package(ROOT, activation_record_path=record_path)


@pytest.mark.parametrize("timestamp", ["2026-07-11T23:59:59Z", "2026-07-12T00:00:00Z"])
def test_activation_timestamp_before_or_at_commit_fails_closed(tmp_path, timestamp):
    record_path = _prepared_record(tmp_path)
    record = _json(record_path)
    record["status"] = "activation_requirements_complete"
    record["committed_at_utc"] = vrt_activation.ACTIVATION_RECORD_CREATION_UTC
    record["prospective_activation_at_utc"] = timestamp
    _write_json(record_path, record)

    with pytest.raises(vrt_activation.ActivationConformanceError, match="activation timestamp"):
        vrt_activation.validate_activation_package(ROOT, activation_record_path=record_path)


def test_canonical_activation_hash_is_independent_of_dictionary_order():
    record = _json(RECORD)
    reordered = dict(reversed(list(record.items())))

    assert vrt_activation.canonical_json_sha256(record) == vrt_activation.canonical_json_sha256(reordered)


def test_first_observation_schema_is_deterministic_and_unpopulated():
    schema = _json(OBSERVATION)

    vrt_activation.validate_first_observation_schema(schema)
    assert vrt_activation.canonical_json_sha256(schema) == vrt_activation.canonical_json_sha256(copy.deepcopy(schema))
