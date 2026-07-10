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

## Edge V2 MT5 research pipeline

Export local MT5 history, backtest it, and generate a diagnostic-only report:
```bash
python -m trading_bot.research.edge_v2_mt5_pipeline --symbol XAUUSD --timeframe M5 --start 2026-05-18T19:10:00+00:00 --end 2026-07-10T01:40:00+00:00 --out-dir reports/edge_v2_mt5_xauusd_m5
```
It writes local candles, journal, and JSON report artifacts. `environment_blocked`
means the local terminal cannot provide the requested history; no fallback data or
diagnostic claim is produced.

## Edge V2 cohort diagnostics and fixed replication

`edge_v2_cohort_report` assigns numeric values to mutually exclusive, stable-rank
`bottom_25`, `middle_50`, and `top_25` buckets. Its
`cohort_assignment_diagnostics` records counts, overlap checks, distribution
degeneracy, and whether ties would have inflated the former threshold-group
method; a positive cohort remains diagnostic only.

Replicate the fixed `lower_quartile_closes=bottom_25` cohort across existing batch
outputs without searching thresholds:
```bash
python -m trading_bot.research.edge_v2_cohort_replication --batch-output reports/edge_v2_batch --out reports/edge_v2_fixed_cohort_replication.json
```
The report is diagnostic-only and does not recommend strategy changes.

## Edge V2 fixed signal robustness

Compare the preselected `lower_quartile_closes` signal by raw values, fixed
cumulative groups, rank diagnostics, time splits, and a first-half calibration
applied to the second half:
```bash
python -m trading_bot.research.edge_v2_fixed_signal_robustness --batch-dir reports/edge_v2_batch --out reports/edge_v2_batch/lower_quartile_closes_robustness.json
```
Raw values are observable; a rank `bottom_25` bucket is diagnostic and not a
directly tradable threshold. A single calibration/test split is not edge confirmation.

## Edge V2 conditional failure analysis

Inspect winners and losers inside the preselected `lower_quartile_closes == 0`
slice, including a compact casebook for manual TradingView review:
```bash
python -m trading_bot.research.edge_v2_conditional_failure_analysis --batch-dir reports/edge_v2_batch --condition lower_quartile_closes_eq_0 --out reports/edge_v2_batch/lqc0_failure_analysis.json
```
The companion casebook JSON is written beside the report. It is diagnostic-only:
the slice is not a trading rule and any apparent discriminator needs more research.

## Edge V2 candidate discriminator audit

Audit only the preselected `risk_points`, `candle_range`, and `reward_points`
inside the same slice, with conservative leakage labels and report-only ratios:
```bash
python -m trading_bot.research.edge_v2_candidate_discriminator_audit --batch-dir reports/edge_v2_batch --condition lower_quartile_closes_eq_0 --out reports/edge_v2_batch/lqc0_discriminator_audit.json
```
Unknown timing remains unknown; normalized groups and calibration diagnostics are
research aids, not strategy rules.
