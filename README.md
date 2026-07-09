# Modular Python Trading Lab

A hardened, modular, platform-agnostic algorithmic trading lab designed for research and analysis.

## Modes of Operation

### 1. Analysis-Only Mode (Strict Default)
The bot operates in a strict analysis flow. It:
- Fetches market data (Mock or MT5).
- Runs signal detection (Liquidity Sweeps).
- Passes setups through risk guards (Spread, Volatility, Session Limits).
- **Publishes a structured JSON recommendation to `output/`.**

**Safety Guarantees:**
- `submit_allowed` is always `false`.
- `broker_api_called` is always `false`.
- `live_execution_enabled` is always `false`.
- The execution path is fully decoupled and unreachable from the analysis flow.
- **Explicit Data Provider selection**: Default is `mock`. MT5 must be explicitly enabled and configured.

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_PROVIDER` | `mock` | `mock` or `mt5` |
| `MOCK_SCENARIO` | `no_setup` | `no_setup`, `high_sweep`, `low_sweep` |
| `BLOCK_IF_DATA_MISSING` | `true` | Blocks setups if spread/volatility is null |
| `ANALYSIS_ONLY` | `true` | Enforces analysis flow |

## Why Platform Agnostic?
The core architecture is designed so that the strategy logic and risk management are independent of the broker. This allows for a future migration to institutional-grade platforms like **Sierra Chart** using the **Denali Exchange Data Feed** with minimal code changes.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env`.
3. Run the lab:
   ```bash
   python main.py
   ```

## Documentation
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)

## Testing
Run the suite with:
```bash
export PYTHONPATH=$PYTHONPATH:.
python -m pytest tests -q
```

## Edge V2 feature separation

Generate a diagnostic-only JSON comparison of winners and losers from an
existing journal or CSV export:
```bash
python -m trading_bot.research.edge_v2_feature_separation --journal logs/xauusd_m5/trades.jsonl --out reports/edge_v2_feature_separation.json
```
