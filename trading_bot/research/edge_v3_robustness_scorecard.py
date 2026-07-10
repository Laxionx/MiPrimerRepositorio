"""Conservative Edge V3 robustness scorecard; never emits a trading rule."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


MIN_TOTAL_TRADES = 100
MIN_WINNERS = 10
MIN_LOSERS = 10
MIN_INDEPENDENT_SEGMENTS = 3
MAX_SEGMENT_CONCENTRATION = 0.5


def build_robustness_scorecard(
    matrix: dict[str, Any], discovery: dict[str, Any], train_test: dict[str, Any]
) -> dict[str, Any]:
    records = list(matrix.get("records", []))
    concentration = _symbol_timeframe_concentration(records)
    features = {}
    for name, report in discovery.get("features", {}).items():
        global_report = report.get("global", {})
        temporal_summary = _temporal_summary(train_test, name)
        outlier = global_report.get("outlier_sensitivity", {})
        features[name] = score_feature(
            name,
            provenance=matrix.get("feature_provenance", {}).get(name, report.get("provenance", {})),
            sample={"count": global_report.get("count", 0), "winner_count": global_report.get("winners", 0), "loser_count": global_report.get("losers", 0)},
            sign_summary=report.get("consistency", {}),
            temporal_summary=temporal_summary,
            concentration=concentration,
            outlier_conflict=bool(outlier.get("material_conflict")),
        )
    rejected = sorted(name for name, result in features.items() if result["decision"] == "rejected")
    frozen = sorted(name for name, result in features.items() if result["decision"] == "frozen")
    promoted = sorted(name for name, result in features.items() if result["decision"] == "candidate_discriminator_hypothesis")
    return {
        "schema_version": "aqtf_edge_v3_robustness_scorecard.v1",
        "diagnostic_only": True,
        "lqc_excluded": True,
        "symbol_timeframe_concentration": concentration,
        "features": features,
        "rejected_features": rejected,
        "frozen_features": frozen,
        "candidate_discriminator_hypotheses": promoted,
        "candidate_rule_report": "not_created",
        "disclaimer": "A candidate discriminator hypothesis is descriptive only and is not a trading rule or an edge confirmation.",
    }


def score_feature(
    name: str, *, provenance: dict[str, Any], sample: dict[str, Any], sign_summary: dict[str, Any],
    temporal_summary: dict[str, Any], concentration: float, outlier_conflict: bool,
) -> dict[str, Any]:
    reasons = []
    strict = _strict(provenance)
    sufficient = (
        int(sample.get("count", 0)) >= MIN_TOTAL_TRADES
        and int(sample.get("winner_count", 0)) >= MIN_WINNERS
        and int(sample.get("loser_count", 0)) >= MIN_LOSERS
    )
    positive, negative = int(sign_summary.get("positive", 0)), int(sign_summary.get("negative", 0))
    independent = int(sign_summary.get("independent_segments", positive + negative))
    materially_mixed = positive > 0 and negative > 0
    if name == "lower_quartile_closes":
        reasons.append("lower_quartile_closes_is_permanently_excluded")
    if not strict:
        reasons.append("strict_provenance_required")
    if not sufficient:
        reasons.append("insufficient_sample")
    if temporal_summary.get("sufficient") and not temporal_summary.get("non_negative"):
        reasons.append("negative_test_performance")
    if concentration > MAX_SEGMENT_CONCENTRATION:
        reasons.append("single_symbol_timeframe_concentration")
    if outlier_conflict:
        reasons.append("mean_median_or_trimmed_mean_conflict")
    if reasons:
        decision = "rejected"
    elif materially_mixed or not temporal_summary.get("sufficient") or independent < MIN_INDEPENDENT_SEGMENTS:
        decision = "frozen"
        reasons.append("mixed_or_incomplete_replication")
    elif temporal_summary.get("non_negative") and positive >= MIN_INDEPENDENT_SEGMENTS:
        decision = "candidate_discriminator_hypothesis"
    else:
        decision = "frozen"
        reasons.append("insufficient_positive_replication")
    return {
        "decision": decision, "reasons": reasons, "strict_provenance": strict,
        "sample_sufficient": sufficient, "sign_summary": {"positive": positive, "negative": negative, "independent_segments": independent},
        "temporal_summary": temporal_summary, "symbol_timeframe_concentration": concentration,
        "outlier_conflict": outlier_conflict,
    }


def _temporal_summary(train_test: dict[str, Any], feature: str) -> dict[str, Any]:
    reports = train_test.get("segments", {}).get("symbol_timeframe", [])
    if not reports:
        return {"sufficient": False, "non_negative": False, "eligible_cohorts": 0}
    results = []
    for report in reports:
        cohorts = list(report.get("features", {}).get(feature, {}).get("cohorts", {}).values())
        eligible = [item["test"] for item in cohorts if not item.get("sample_size_warning")]
        if eligible:
            results.append(all((item.get("expectancy") or 0) >= 0 and (item.get("profit_factor") or 0) >= 1 for item in eligible))
    return {
        "sufficient": bool(results), "non_negative": bool(results) and all(results),
        "eligible_cohorts": len(results), "positive_segments": sum(results),
        "negative_segments": len(results) - sum(results),
    }


def _symbol_timeframe_concentration(records: list[dict[str, Any]]) -> float:
    if not records:
        return 1.0
    counts = Counter(
        f"{row.get('segment', {}).get('symbol')}/{row.get('segment', {}).get('timeframe')}"
        for row in records
    )
    return max(counts.values()) / len(records)


def _strict(provenance: dict[str, Any]) -> bool:
    return (
        provenance.get("source_basis") == "code_verified"
        and provenance.get("availability_timing") == "pre_trade"
        and provenance.get("leakage_risk") == "low"
    )


def write_summary(scorecard: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Edge V3 Research Summary", "", "Diagnostic-only. No Candidate Rule Report is created.", "",
        f"- Rejected: {len(scorecard['rejected_features'])}",
        f"- Frozen: {len(scorecard['frozen_features'])}",
        f"- Candidate Discriminator Hypotheses: {len(scorecard['candidate_discriminator_hypotheses'])}",
        "", "Las interacciones 2D quedan diferidas hasta que una o más features pasen los gates univariados.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(value: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a conservative Edge V3 robustness scorecard")
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--train-test", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args(argv)
    score = build_robustness_scorecard(_read_json(args.matrix), _read_json(args.discovery), _read_json(args.train_test))
    _write_json(score, args.out)
    write_summary(score, args.summary_out)
    print(args.out)


if __name__ == "__main__":
    main()
