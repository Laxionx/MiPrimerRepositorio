# Architecture: Algorithmic Trading Lab

This project is designed as a modular lab for developing and testing algorithmic trading strategies. While it starts with MetaTrader 5 (MT5) as the primary operational environment, the architecture is platform-agnostic.

## Core Design Principles

1.  **Modularity**: Clear separation between Data, Signals, Risk, and Output.
2.  **Platform Agnostic**: Interfaces allow swapping MT5 for other platforms (Sierra Chart, OANDA, etc.) with minimal changes.
3.  **Safety First**: Analysis-only mode is the default and only flow. No live execution path is reachable.
4.  **Auditability**: Every detection generates a structured JSON recommendation with a unique `run_id` and `schema_version`.

## Hardened Configuration

- `DATA_PROVIDER`: Explicitly chooses between `mock` and `mt5`. Default is `mock`. Instantiating `MT5DataProvider` requires this to be set to `mt5` AND valid credentials.
- `MOCK_SCENARIO`: Selects deterministic data scenarios for testing (`no_setup`, `high_sweep`, `low_sweep`).
- `BLOCK_IF_DATA_MISSING`: Safety guard that blocks setups if market context (spread/volatility) is unavailable.

## Component Breakdown

### 1. Market Data Provider (`MarketDataProvider`)
Responsible for fetching OHLCV data and market context (spread, volatility).
- `MT5DataProvider`: Uses the MetaTrader5 Python package.
- `MockDataProvider`: Generates synthetic deterministic data for testing.
- `Data Factory`: Centralized logic for provider selection in `trading_bot/data/factory.py`.

### 2. Signal Detector (`SignalDetector`)
Implements strategy logic. It consumes OHLCV data and produces a potential `setup`.
- `LiquiditySweepDetector`: Implementation detecting price sweeps of recent highs/lows with manual VWAP.

### 3. Risk Guard (`RiskGuard`)
Validates setups against risk rules (max loss, spread limits, volatility).
- `SimpleRiskGuard`: Enforces daily limits and market condition filters using context from the Data Provider. Blocks on missing data if configured.

### 4. Recommendation Publisher (`RecommendationPublisher`)
Formats and exports the result of the analysis.
- `JSONRecommendationPublisher`: Saves the structured lab output (v1.1.0) to the `output/` directory.

## Sierra Chart / Denali Migration Path

To migrate to Sierra Chart / Denali:
1. Implement a new `MarketDataProvider` that communicates with Sierra Chart (e.g., via DTC protocol or file-based bridge).
2. The `SignalDetector` and `RiskGuard` remain unchanged, as they only depend on the abstract interfaces.
