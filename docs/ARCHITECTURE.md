# Architecture: Algorithmic Trading Lab

This project is designed as a modular lab for developing and testing algorithmic trading strategies. While it starts with MetaTrader 5 (MT5) as the primary operational environment, the architecture is platform-agnostic.

## Core Design Principles

1.  **Modularity**: Clear separation between Data, Signals, Risk, and Execution.
2.  **Platform Agnostic**: Interfaces allow swapping MT5 for other platforms (Sierra Chart, OANDA, etc.) with minimal changes.
3.  **Safety First**: Analysis-only mode is the default. Live execution must be explicitly enabled.
4.  **Auditability**: Every detection generates a structured JSON recommendation for audit and review.

## Component Breakdown

### 1. Market Data Provider (`MarketDataProvider`)
Responsible for fetching OHLCV data.
- `MT5DataProvider`: Uses the MetaTrader5 Python package.
- `MockDataProvider`: Generates synthetic data for testing.
- *Future*: `SierraChartDataProvider` could be implemented to fetch data via Denali Exchange Data Feed.

### 2. Signal Detector (`SignalDetector`)
Implements strategy logic. It consumes OHLCV data and produces a potential `setup`.
- `LiquiditySweepDetector`: Current implementation detecting price sweeps of recent highs/lows.

### 3. Risk Guard (`RiskGuard`)
Validates setups against risk rules (max loss, spread limits, volatility).
- `SimpleRiskGuard`: Enforces daily limits and market condition filters.

### 4. Recommendation Publisher (`RecommendationPublisher`)
Formats and exports the result of the analysis.
- `JSONRecommendationPublisher`: Saves the structured lab output to the `output/` directory.

### 5. Executor (`Executor`)
Handles trade execution.
- `DryRunExecutor`: Simulates execution in logs.
- `MT5Executor`: (Disabled by default) Sends real orders to MT5 terminal.

## Sierra Chart / Denali Migration Path

To migrate to Sierra Chart / Denali:
1. Implement a new `MarketDataProvider` that communicates with Sierra Chart (e.g., via DTC protocol or file-based bridge).
2. Implement a new `Executor` for Sierra Chart.
3. The `SignalDetector` and `RiskGuard` remain unchanged, as they only depend on the abstract interfaces.
