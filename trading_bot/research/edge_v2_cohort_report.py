from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any

from trading_bot.research.edge_v2_feature_separation import load_journal_records


FEATURES = ("lower_quartile_closes", "price_position_in_range", "pressure_score", "prior_range_points", "compression_score", "directional_pressure_score", "reclaim_speed", "sweep_depth")
PAIRS = (("price_position_in_range", "pressure_score", "top_25", "top_25"), ("price_position_in_range", "lower_quartile_closes", "top_25", "bottom_25"), ("pressure_score", "lower_quartile_closes", "top_25", "bottom_25"), ("prior_range_points", "pressure_score", "bottom_25", "top_25"))


def analyze_cohorts(records: list[dict[str, Any]]) -> dict[str, Any]:
    available = [f for f in FEATURES if any(_num(r.get(f)) is not None for r in records)]
    cohorts = {f: _feature_cohorts(records, f) for f in available}
    pairs = {}
    for left, right, left_group, right_group in PAIRS:
        if left in cohorts and right in cohorts:
            selected = [r for r in records if r in cohorts[left][left_group]["_records"] and r in cohorts[right][right_group]["_records"]]
            pairs[f"{left}_{left_group}__{right}_{right_group}"] = cohort_metrics(selected)
    for groups in cohorts.values():
        for value in groups.values():
            value.pop("_records", None)
    return {
        "schema_version": "aqtf_edge_v2_cohort.v1", "diagnostic_only": True,
        "trade_count": len(records), "unavailable_features": [f for f in FEATURES if f not in available],
        "single_feature_cohorts": cohorts, "pairwise_cohorts": pairs,
        "best_single_feature_cohorts_by_expectancy": _rank(cohorts, "expectancy"),
        "best_pairwise_cohorts_by_expectancy": _rank_pairs(pairs, "expectancy"),
        "cohorts_rejected_for_low_sample": _flagged(cohorts, pairs, "insufficient_data"),
        "cohorts_with_negative_expectancy": _flagged(cohorts, pairs, "negative"),
        "cohorts_with_pf_below_1": _pf(cohorts, pairs, lambda value: value is not None and value < 1),
        "cohorts_with_pf_above_1_but_insufficient_sample": _pf(cohorts, pairs, lambda value: value is not None and value > 1, require_insufficient=True),
        "disclaimer": "Diagnostic only; positive cohorts are not strategy rules or confirmed edges.",
    }


def _feature_cohorts(records, feature):
    values = sorted(_num(r.get(feature)) for r in records if _num(r.get(feature)) is not None)
    if not values:
        return {}
    low, high = _quantile(values, .25), _quantile(values, .75)
    groups = {"bottom_25": [r for r in records if (_num(r.get(feature)) is not None and _num(r[feature]) <= low)], "middle_50": [r for r in records if (_num(r.get(feature)) is not None and low < _num(r[feature]) < high)], "top_25": [r for r in records if (_num(r.get(feature)) is not None and _num(r[feature]) >= high)]}
    return {name: {**cohort_metrics(rows), "_records": rows} for name, rows in groups.items()}


def cohort_metrics(rows):
    pnl = [float(r.get("pnl", 0)) for r in rows]
    wins, losses = [x for x in pnl if x > 0], [x for x in pnl if x < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    count, wc, lc = len(pnl), len(wins), len(losses)
    pf = gross_profit / gross_loss if gross_loss else None
    expectancy = sum(pnl) / count if count else 0.0
    insufficient = count < 20 or wc < 5 or lc < 5
    flag = "insufficient_data" if insufficient else "negative" if expectancy < 0 and (pf or 0) < 1 else "neutral" if abs(expectancy) < .01 or (pf is not None and .9 <= pf <= 1.1) else "promising_but_unconfirmed" if expectancy > 0 and (pf or 0) > 1.2 else "weak_positive"
    return {"trade_count": count, "winner_count": wc, "loser_count": lc, "breakeven_count": count-wc-lc, "win_rate": wc/count if count else 0, "gross_profit": gross_profit, "gross_loss": gross_loss, "profit_factor": pf, "expectancy": expectancy, "average_win": sum(wins)/wc if wc else None, "average_loss": sum(losses)/lc if lc else None, "median_pnl": median(pnl) if pnl else None, "max_win": max(wins) if wins else None, "max_loss": min(losses) if losses else None, "payoff_ratio": (sum(wins)/wc)/abs(sum(losses)/lc) if wins and losses else None, "diagnostic_only": True, "sample_size_warning": insufficient, "min_trade_count_met": count >= 20, "min_winner_count_met": wc >= 5, "min_loser_count_met": lc >= 5, "interpretation": flag}


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _quantile(v, q):
    return v[int(len(v) * q) - 1 if q < 0.5 else int(len(v) * q)]
def _rank(groups, key): return sorted([f"{f}_{g}" for f, gs in groups.items() for g, x in gs.items()], key=lambda name: next(x[key] for f, gs in groups.items() for g, x in gs.items() if f"{f}_{g}" == name), reverse=True)
def _rank_pairs(pairs, key): return sorted(pairs, key=lambda name: pairs[name][key], reverse=True)
def _flagged(groups, pairs, flag): return [n for n in _rank(groups, "expectancy") if next(x["interpretation"] for f, gs in groups.items() for g, x in gs.items() if f"{f}_{g}" == n) == flag] + [n for n,x in pairs.items() if x["interpretation"] == flag]
def _pf(groups, pairs, predicate, require_insufficient=False): return [n for n in _rank(groups, "expectancy") if predicate(next(x["profit_factor"] for f,gs in groups.items() for g,x in gs.items() if f"{f}_{g}"==n)) and (not require_insufficient or next(x["interpretation"] for f,gs in groups.items() for g,x in gs.items() if f"{f}_{g}"==n)=="insufficient_data")]

def main():
    p = argparse.ArgumentParser(description="Generate diagnostic-only Edge V2 cohort report")
    p.add_argument("--journal", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    report = analyze_cohorts(load_journal_records(a.journal))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2))
    print(a.out)


if __name__ == "__main__":
    main()

