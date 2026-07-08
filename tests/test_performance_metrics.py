import json
import subprocess
import sys
from pathlib import Path

import pytest

from trading_bot.metrics.performance import calculate_performance_metrics


def test_metrics_support_empty_history():
    metrics = calculate_performance_metrics([])

    assert metrics == {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_pnl": 0.0,
        "average_win": 0.0,
        "average_loss": 0.0,
        "expectancy": 0.0,
        "profit_factor": None,
        "max_drawdown": 0.0,
        "average_r": 0.0,
        "largest_loss": None,
        "largest_win": None,
    }


def test_metrics_support_winning_and_losing_trades():
    trades = [
        {"pnl": 100.0, "risk_amount": 50.0},
        {"pnl": -40.0, "risk_amount": 40.0},
        {"pnl": 60.0, "r_multiple": 2.0},
        {"pnl": -20.0, "r_multiple": -0.5},
    ]

    metrics = calculate_performance_metrics(trades)

    assert metrics["total_trades"] == 4
    assert metrics["wins"] == 2
    assert metrics["losses"] == 2
    assert metrics["win_rate"] == 0.5
    assert metrics["gross_profit"] == 160.0
    assert metrics["gross_loss"] == -60.0
    assert metrics["net_pnl"] == 100.0
    assert metrics["average_win"] == 80.0
    assert metrics["average_loss"] == -30.0
    assert metrics["expectancy"] == 25.0
    assert metrics["profit_factor"] == pytest.approx(160 / 60)
    assert metrics["max_drawdown"] == 40.0
    assert metrics["average_r"] == pytest.approx(0.625)
    assert metrics["largest_loss"] == -40.0
    assert metrics["largest_win"] == 100.0


def test_report_script_prints_empty_metrics_for_missing_default_history(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "report_metrics.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    metrics = json.loads(result.stdout)

    assert metrics["total_trades"] == 0
    assert metrics["net_pnl"] == 0.0
