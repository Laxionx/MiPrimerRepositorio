# Modular Python Trading Bot

A simple, modular trading bot designed for MetaTrader 5, but extensible to other platforms.

## Architecture

- **Core**: Orchestrates the bot's workflow.
- **Data**: Providers for market data (MT5, Mock).
- **Strategy**: Logic for generating trading signals.
- **Risk**: Rules for managing trade risk.
- **Execution**: Modules for executing trades (MT5, Dry Run).
- **Utils**: Logging and other utilities.
- **Config**: Settings management.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your MT5 credentials.
3. Run the bot:
   ```bash
   python main.py
   ```

## Dry Run Mode

By default, the bot runs in dry-run mode (`LIVE_TRADING=false`). It will simulate execution without placing real orders.

## Testing

Run tests with:
```bash
python -m unittest discover tests
```
