# Modular Python Trading Lab

A modular, platform-agnostic algorithmic trading lab designed for research, analysis, and automated execution.

## Modes of Operation

The bot is designed to prioritize safety and auditability.

### 1. Analysis-Only Mode (Default)
In this mode (`ANALYSIS_ONLY=true`), the bot:
- Fetches market data.
- Runs signal detection.
- Passes setups through risk guards.
- **Publishes a structured JSON recommendation to `output/`.**
- **Never calls broker APIs.**
- **Does not execute trades.**

### 2. Dry-Run Mode
When `ANALYSIS_ONLY=false` and `LIVE_TRADING=false`, the bot:
- Operates normally but uses the `DryRunExecutor`.
- Simulates execution in the logs without sending real orders.

### 3. Live Trading Mode
When `ANALYSIS_ONLY=false` and `LIVE_TRADING=true`, the bot:
- Sends real orders to the configured broker (e.g., MetaTrader 5).
- **Requires valid credentials and explicit user enablement.**

## Why MetaTrader 5 (MT5)?
MT5 is used as the first operational lab environment because it provides an easy-to-use Python API for both data and execution across many asset classes.

## Why Platform Agnostic?
The core architecture is designed so that the strategy logic and risk management are independent of the broker. This allows for a future migration to institutional-grade platforms like **Sierra Chart** using the **Denali Exchange Data Feed** with minimal code changes.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env`.
3. Run the lab in analysis mode:
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
python -m unittest discover tests
```
