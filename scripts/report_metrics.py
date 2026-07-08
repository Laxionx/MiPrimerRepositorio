import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.metrics.performance import calculate_performance_metrics  # noqa: E402


def load_trades(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    if path.suffix.lower() == ".json":
        payload = json.loads(content)
        if not isinstance(payload, list):
            raise ValueError("JSON trade history must contain a list")
        return payload
    return [json.loads(line) for line in content.splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Report paper/DEMO trade metrics")
    parser.add_argument(
        "history",
        nargs="?",
        type=Path,
        default=Path("runtime/trades.jsonl"),
    )
    args = parser.parse_args()
    metrics = calculate_performance_metrics(load_trades(args.history))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
