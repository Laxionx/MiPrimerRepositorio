from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import Any

from trading_bot.research.edge_v2_feature_separation import load_journal_records


FEATURES = (
    "lower_quartile_closes",
    "price_position_in_range",
    "pressure_score",
    "prior_range_points",
    "compression_score",
    "directional_pressure_score",
    "reclaim_speed",
    "sweep_depth",
)
BUCKETS = ("bottom_25", "middle_50", "top_25")
PAIRS = (
    ("price_position_in_range", "pressure_score", "top_25", "top_25"),
    ("price_position_in_range", "lower_quartile_closes", "top_25", "bottom_25"),
    ("pressure_score", "lower_quartile_closes", "top_25", "bottom_25"),
    ("prior_range_points", "pressure_score", "bottom_25", "top_25"),
)


def analyze_cohorts(records: list[dict[str, Any]]) -> dict[str, Any]:
    available = [feature for feature in FEATURES if _has_numeric_value(records, feature)]
    assignments = {
        feature: _assign_feature_buckets(records, feature) for feature in available
    }
    cohorts = {
        feature: _cohort_metrics_by_bucket(assignment["buckets"])
        for feature, assignment in assignments.items()
    }
    pairs = _pairwise_cohorts(assignments)
    return {
        "schema_version": "aqtf_edge_v2_cohort.v2",
        "diagnostic_only": True,
        "trade_count": len(records),
        "unavailable_features": [feature for feature in FEATURES if feature not in available],
        "cohort_assignment_method": "stable_rank_partition",
        "cohort_assignment_diagnostics": {
            feature: assignment["diagnostics"]
            for feature, assignment in assignments.items()
        },
        "single_feature_cohorts": cohorts,
        "pairwise_cohorts": pairs,
        "best_single_feature_cohorts_by_expectancy": _rank(cohorts, "expectancy"),
        "best_single_feature_cohorts_by_profit_factor": _rank(
            cohorts, "profit_factor"
        ),
        "best_pairwise_cohorts_by_expectancy": _rank_pairs(pairs, "expectancy"),
        "best_pairwise_cohorts_by_profit_factor": _rank_pairs(
            pairs, "profit_factor"
        ),
        "cohorts_rejected_for_low_sample": _flagged(
            cohorts, pairs, "insufficient_data"
        ),
        "cohorts_with_negative_expectancy": _flagged(cohorts, pairs, "negative"),
        "cohorts_with_pf_below_1": _pf(
            cohorts, pairs, lambda value: value is not None and value < 1
        ),
        "cohorts_with_pf_above_1_but_insufficient_sample": _pf(
            cohorts,
            pairs,
            lambda value: value is not None and value > 1,
            require_insufficient=True,
        ),
        "disclaimer": (
            "Diagnostic only; positive cohorts are not strategy rules or confirmed edges."
        ),
    }


def select_fixed_cohort_records(
    records: list[dict[str, Any]], feature: str, bucket: str
) -> list[dict[str, Any]]:
    """Select a fixed, deterministic feature bucket without threshold optimization."""
    if bucket not in BUCKETS:
        raise ValueError(f"Unknown cohort bucket: {bucket}")
    return _assign_feature_buckets(records, feature)["buckets"][bucket]


def select_fixed_pair_records(
    records: list[dict[str, Any]],
    left_feature: str,
    left_bucket: str,
    right_feature: str,
    right_bucket: str,
) -> list[dict[str, Any]]:
    left = select_fixed_cohort_records(records, left_feature, left_bucket)
    right_ids = {id(record) for record in select_fixed_cohort_records(records, right_feature, right_bucket)}
    return [record for record in left if id(record) in right_ids]


def cohort_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [float(row.get("pnl", 0)) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    count = len(pnl)
    winner_count = len(wins)
    loser_count = len(losses)
    profit_factor = gross_profit / gross_loss if gross_loss else None
    expectancy = sum(pnl) / count if count else 0.0
    insufficient = count < 20 or winner_count < 5 or loser_count < 5
    flag = _interpretation_flag(expectancy, profit_factor, insufficient)
    average_win = sum(wins) / winner_count if winner_count else None
    average_loss = sum(losses) / loser_count if loser_count else None
    return {
        "trade_count": count,
        "winner_count": winner_count,
        "loser_count": loser_count,
        "breakeven_count": count - winner_count - loser_count,
        "win_rate": winner_count / count if count else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "average_win": average_win,
        "average_loss": average_loss,
        "median_pnl": median(pnl) if pnl else None,
        "max_win": max(wins) if wins else None,
        "max_loss": min(losses) if losses else None,
        "payoff_ratio": average_win / abs(average_loss) if wins and losses else None,
        "diagnostic_only": True,
        "sample_size_warning": insufficient,
        "min_trade_count_met": count >= 20,
        "min_winner_count_met": winner_count >= 5,
        "min_loser_count_met": loser_count >= 5,
        "interpretation_flag": flag,
        "interpretation": flag,
    }


def _assign_feature_buckets(
    records: list[dict[str, Any]], feature: str
) -> dict[str, Any]:
    eligible = [
        (index, record, value)
        for index, record in enumerate(records)
        if (value := _num(record.get(feature))) is not None
    ]
    ordered = sorted(eligible, key=lambda item: (item[2], item[0]))
    non_null_count = len(ordered)
    bottom_count = non_null_count // 4
    top_count = non_null_count // 4
    middle_count = non_null_count - bottom_count - top_count
    bucket_rows = {
        "bottom_25": [item[1] for item in ordered[:bottom_count]],
        "middle_50": [
            item[1] for item in ordered[bottom_count : bottom_count + middle_count]
        ],
        "top_25": [item[1] for item in ordered[bottom_count + middle_count :]],
    }
    values = [item[2] for item in ordered]
    diagnostics = _assignment_diagnostics(
        feature=feature,
        records=records,
        ordered=ordered,
        buckets=bucket_rows,
    )
    return {"buckets": bucket_rows, "diagnostics": diagnostics, "values": values}


def _assignment_diagnostics(
    *,
    feature: str,
    records: list[dict[str, Any]],
    ordered: list[tuple[int, dict[str, Any], float]],
    buckets: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    values = [item[2] for item in ordered]
    non_null_count = len(values)
    bucket_counts = {name: len(buckets[name]) for name in BUCKETS}
    bucket_ids = {name: {id(row) for row in buckets[name]} for name in BUCKETS}
    overlaps = {
        "bottom_25_middle_50": len(bucket_ids["bottom_25"] & bucket_ids["middle_50"]),
        "bottom_25_top_25": len(bucket_ids["bottom_25"] & bucket_ids["top_25"]),
        "middle_50_top_25": len(bucket_ids["middle_50"] & bucket_ids["top_25"]),
    }
    overlap_count = sum(overlaps.values())
    covered_count = len(set().union(*bucket_ids.values())) if bucket_ids else 0
    bottom_cut = ordered[len(buckets["bottom_25"]) - 1][2] if buckets["bottom_25"] else None
    top_cut = ordered[-len(buckets["top_25"])][2] if buckets["top_25"] else None
    legacy_would_inflate = _ties_inflate_boundary(
        values, bottom_cut, bucket_counts["bottom_25"]
    )
    legacy_would_inflate = legacy_would_inflate or _ties_inflate_boundary(
        values, top_cut, bucket_counts["top_25"], upper=True
    )
    unique_count = len(set(values))
    warnings = _assignment_warnings(
        non_null_count=non_null_count,
        unique_count=unique_count,
        bucket_counts=bucket_counts,
        overlap_count=overlap_count,
        legacy_would_inflate=legacy_would_inflate,
    )
    return {
        "feature": feature,
        "assignment_method": "stable_rank_partition",
        "thresholds": {
            "q25": _percentile(values, 0.25),
            "q50": _percentile(values, 0.50),
            "q75": _percentile(values, 0.75),
            "bottom_upper_value": bottom_cut,
            "top_lower_value": top_cut,
        },
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "unique_value_count": unique_count,
        "null_count": len(records) - non_null_count,
        "non_null_count": non_null_count,
        "bucket_counts": bucket_counts,
        "bottom_25_count": bucket_counts["bottom_25"],
        "middle_50_count": bucket_counts["middle_50"],
        "top_25_count": bucket_counts["top_25"],
        "overlap_diagnostics": {
            "pairwise_overlap_counts": overlaps,
            "overlap_count_between_buckets": overlap_count,
            "buckets_are_mutually_exclusive": overlap_count == 0,
            "coverage_complete": covered_count == non_null_count,
            "unassigned_count": non_null_count - covered_count,
        },
        "buckets_are_mutually_exclusive": overlap_count == 0,
        "degenerate_distribution": non_null_count > 0 and unique_count == 1,
        "threshold_ties_caused_inflated_cohort_size": False,
        "legacy_threshold_groups_would_be_inflated": legacy_would_inflate,
        "legacy_threshold_group_warnings": (
            ["inflated_bucket_due_to_ties"] if legacy_would_inflate else []
        ),
        "warnings": warnings,
    }


def _cohort_metrics_by_bucket(
    buckets: dict[str, list[dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    return {name: cohort_metrics(rows) for name, rows in buckets.items()}


def _pairwise_cohorts(assignments: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    pairs = {}
    for left, right, left_group, right_group in PAIRS:
        if left not in assignments or right not in assignments:
            continue
        right_ids = {id(row) for row in assignments[right]["buckets"][right_group]}
        selected = [
            row
            for row in assignments[left]["buckets"][left_group]
            if id(row) in right_ids
        ]
        pairs[f"{left}_{left_group}__{right}_{right_group}"] = cohort_metrics(selected)
    return pairs


def _assignment_warnings(
    *,
    non_null_count: int,
    unique_count: int,
    bucket_counts: dict[str, int],
    overlap_count: int,
    legacy_would_inflate: bool,
) -> list[str]:
    warnings = []
    if non_null_count and unique_count == 1:
        warnings.append("degenerate_feature_distribution")
    if legacy_would_inflate:
        warnings.append("threshold_ties_would_inflate_legacy_threshold_groups")
    if overlap_count:
        warnings.append("overlapping_buckets")
    if non_null_count and bucket_counts["middle_50"] == 0:
        warnings.append("empty_middle_bucket")
    if non_null_count and bucket_counts["top_25"] == non_null_count:
        warnings.append("all_values_in_top_bucket")
    if non_null_count and bucket_counts["bottom_25"] == non_null_count:
        warnings.append("all_values_in_bottom_bucket")
    if non_null_count and unique_count < 4:
        warnings.append("insufficient_unique_values")
    return warnings


def _ties_inflate_boundary(
    values: list[float], cutoff: float | None, assigned_count: int, *, upper: bool = False
) -> bool:
    if cutoff is None or assigned_count == 0:
        return False
    threshold_count = sum(value >= cutoff for value in values) if upper else sum(
        value <= cutoff for value in values
    )
    return threshold_count > assigned_count


def _interpretation_flag(
    expectancy: float, profit_factor: float | None, insufficient: bool
) -> str:
    if insufficient:
        return "insufficient_data"
    if expectancy < 0 and (profit_factor or 0) < 1:
        return "negative"
    if abs(expectancy) < 0.01 or (profit_factor is not None and 0.9 <= profit_factor <= 1.1):
        return "neutral"
    if expectancy > 0 and (profit_factor or 0) > 1.2:
        return "promising_but_unconfirmed"
    return "weak_positive"


def _has_numeric_value(records: list[dict[str, Any]], feature: str) -> bool:
    return any(_num(record.get(feature)) is not None for record in records)


def _num(value: Any) -> float | None:
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return number if number is not None and math.isfinite(number) else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    index = (len(values) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def _rank(groups: dict[str, dict[str, dict[str, Any]]], key: str) -> list[str]:
    entries = [
        (f"{feature}_{bucket}", metrics)
        for feature, buckets in groups.items()
        for bucket, metrics in buckets.items()
    ]
    return [name for name, _ in sorted(entries, key=lambda item: _metric_key(item[1], key), reverse=True)]


def _rank_pairs(pairs: dict[str, dict[str, Any]], key: str) -> list[str]:
    return [
        name
        for name, _ in sorted(
            pairs.items(), key=lambda item: _metric_key(item[1], key), reverse=True
        )
    ]


def _metric_key(metrics: dict[str, Any], key: str) -> float:
    value = metrics.get(key)
    return float("-inf") if value is None else float(value)


def _flagged(
    groups: dict[str, dict[str, dict[str, Any]]], pairs: dict[str, dict[str, Any]], flag: str
) -> list[str]:
    singles = [
        name
        for name in _rank(groups, "expectancy")
        if _single_metrics(groups, name)["interpretation_flag"] == flag
    ]
    return singles + [
        name for name, metrics in pairs.items() if metrics["interpretation_flag"] == flag
    ]


def _pf(
    groups: dict[str, dict[str, dict[str, Any]]],
    pairs: dict[str, dict[str, Any]],
    predicate: Any,
    *,
    require_insufficient: bool = False,
) -> list[str]:
    singles = [
        name
        for name in _rank(groups, "expectancy")
        if predicate(_single_metrics(groups, name)["profit_factor"])
        and (
            not require_insufficient
            or _single_metrics(groups, name)["interpretation_flag"] == "insufficient_data"
        )
    ]
    pairs_matched = [
        name
        for name, metrics in pairs.items()
        if predicate(metrics["profit_factor"])
        and (
            not require_insufficient
            or metrics["interpretation_flag"] == "insufficient_data"
        )
    ]
    return singles + pairs_matched


def _single_metrics(
    groups: dict[str, dict[str, dict[str, Any]]], name: str
) -> dict[str, Any]:
    feature, bucket = name.rsplit("_", 2)[0], "_".join(name.rsplit("_", 2)[1:])
    return groups[feature][bucket]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate diagnostic-only Edge V2 cohort report")
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_cohorts(load_journal_records(args.journal))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
