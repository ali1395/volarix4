# Volarix 4 Backtest

API-based backtesting engine for Volarix 4 strategy.

## Overview

This package provides a clean, OOP-based backtesting framework that:

- **API-only signals**: ALL signal generation goes through the HTTP `/signal` endpoint (no direct strategy imports)
- **Realistic execution**: Simulates broker costs (spread, slippage, commission) and partial TPs
- **Deterministic results**: Same bars + API responses = same results every time
- **Clean architecture**: Separated concerns with testable classes

## Architecture

```
volarix4_backtest/
├── config.py          # BacktestConfig and CostModel dataclasses
├── data_source.py     # BarDataSource for loading historical data
├── api_client.py      # SignalApiClient for calling /signal endpoint
├── broker_sim.py      # BrokerSimulator for trade execution
├── engine.py          # BacktestEngine orchestration
├── reporting.py       # Results export (CSV, summary)
├── cli.py             # Command-line interface
├── __init__.py        # Package exports
├── __main__.py        # Module entry point
└── test_no_core_imports.py  # Import guard test
```

## Installation

No installation needed - this is a standalone package within the Volarix 4 repo.

## Usage

### Basic Example

```bash
# Start the API server first (in another terminal)
cd volarix4
python run.py

# Run backtest using MT5 data
python -m volarix4_backtest \
  --symbol EURUSD \
  --timeframe H1 \
  --start 2023-01-01 \
  --end 2023-12-31 \
  --api-url http://localhost:8000
```

### Using CSV/Parquet Data

```bash
# From CSV file
python -m volarix4_backtest \
  --source csv \
  --file ./data/EURUSD_H1.csv \
  --symbol EURUSD \
  --timeframe H1

# From Parquet file
python -m volarix4_backtest \
  --source parquet \
  --file ./data/EURUSD_H1.parquet \
  --symbol EURUSD \
  --timeframe H1
```

### Advanced Options

```bash
python -m volarix4_backtest \
  --symbol EURUSD \
  --timeframe H1 \
  --start 2023-01-01 \
  --end 2023-12-31 \
  --api-url http://localhost:8000 \
  --min-confidence 0.7 \
  --broken-level-cooldown-hours 24 \
  --broken-level-break-pips 15 \
  --min-edge-pips 2.0 \
  --spread-pips 1.5 \
  --slippage-pips 0.5 \
  --commission 3.5 \
  --lot-size 0.01 \
  --initial-balance 10000 \
  --fill-at next_open \
  --output-dir ./results \
  --verbose
```

## Command-Line Arguments

### Trading Pair & Timeframe
- `--symbol`: Trading symbol (default: EURUSD)
- `--timeframe`: Timeframe (H1, M15, D1, etc.) (default: H1)

### Data Source
- `--source`: Data source type (csv, parquet, mt5) (default: mt5)
- `--file`: Path to CSV/Parquet file (required for csv/parquet)
- `--start`: Start date (YYYY-MM-DD)
- `--end`: End date (YYYY-MM-DD)
- `--bars`: Number of most recent bars to load (alternative to date range)

### API Configuration
- `--api-url`: API base URL (default: http://localhost:8000)
- `--api-timeout`: API request timeout in seconds (default: 30.0)
- `--api-max-retries`: Max API request retries (default: 3)
- `--use-legacy-mode`: Send full bar data instead of bar_time
- `--lookback-bars`: Lookback bars for signal generation (default: 400)

### Backtest Parity Parameters
- `--min-confidence`: Minimum confidence threshold
- `--broken-level-cooldown-hours`: Broken level cooldown period (hours)
- `--broken-level-break-pips`: Broken level break threshold (pips)
- `--min-edge-pips`: Minimum edge after costs (pips)

### Cost Model
- `--spread-pips`: Spread cost in pips (default: 1.5)
- `--slippage-pips`: Slippage per execution in pips (default: 0.5)
- `--commission`: Commission per side per lot in USD (default: 3.5)
- `--usd-per-pip`: USD value per pip per lot (default: 10.0)
- `--lot-size`: Position size in lots (default: 0.01)

### Risk Management
- `--initial-balance`: Initial account balance in USD (default: 10000.0)
- `--risk-percent`: Risk per trade as % of balance (default: 1.0)

### Execution Settings
- `--fill-at`: When to fill entries (next_open or signal_close) (default: next_open)
- `--warmup-bars`: Minimum bars before first signal (default: 200)

### Output Settings
- `--output-dir`: Output directory for results (default: ./backtest_results)
- `--no-save-trades`: Don't save trades CSV
- `--no-save-equity`: Don't save equity curve CSV
- `--verbose`: Enable verbose logging

## Fill Model

The backtest uses a **no-peeking** fill model:

- **Signal Generation**: Called at bar close (decision bar)
- **Entry Fill**: Executed at next bar open (default: `--fill-at next_open`)
- **Exit Fills**: Checked on each bar (SL/TP hit detection)

This ensures realistic simulation - you cannot enter at the signal bar close in live trading.

## Cost Model

Costs are applied realistically:

- **Entry**: Spread + Slippage applied to entry price
- **Exit**: Slippage applied to exit price (no spread)
- **Commission**: Applied per side per lot (entry + exit)

Total round-trip cost = spread + (2 × slippage) + (2 × commission × lot_size)

## Partial TPs

The backtest supports partial take-profits using percentages from the API:

- **TP1**: Close `tp1_percent` of position (e.g., 50%)
- **TP2**: Close `tp2_percent` of position (e.g., 30%)
- **TP3**: Close `tp3_percent` of position (e.g., 20%)

P&L is calculated for each partial close separately, with exit costs applied proportionally.

## Output Files

Results are saved to `--output-dir` with timestamped filenames:

- `{symbol}_{timeframe}_{timestamp}_trades.csv`: Trade-by-trade log
- `{symbol}_{timeframe}_{timestamp}_equity.csv`: Equity curve data
- `{symbol}_{timeframe}_{timestamp}_summary.txt`: Performance summary

## Import Guard

The package includes a test to prevent accidental strategy logic imports:

```bash
cd volarix4_backtest
python test_no_core_imports.py
```

This ensures **zero imports** of `volarix4.core.*` modules (except `fetch_ohlc` for MT5 data loading).

## Example Workflow

1. **Start API server**:
   ```bash
   cd volarix4
   python run.py
   ```

2. **Run backtest**:
   ```bash
   python -m volarix4_backtest --symbol EURUSD --timeframe H1 --bars 5000 --verbose
   ```

3. **Check results**:
   ```bash
   ls backtest_results/
   # EURUSD_H1_20260101_120000_trades.csv
   # EURUSD_H1_20260101_120000_equity.csv
   # EURUSD_H1_20260101_120000_summary.txt
   ```

## Programmatic Usage

```python
from volarix4_backtest import (
    BacktestConfig,
    BarDataSource,
    SignalApiClient,
    BrokerSimulator,
    BacktestEngine,
    BacktestReporter
)

# Create config
config = BacktestConfig(
    symbol="EURUSD",
    timeframe="H1",
    bars=5000,
    api_url="http://localhost:8000"
)

# Create components
data_source = BarDataSource(source="mt5", symbol="EURUSD", timeframe="H1", bars=5000)
data_source.load()

api_client = SignalApiClient(base_url="http://localhost:8000")
broker = BrokerSimulator(
    spread_pips=1.5,
    slippage_pips=0.5,
    commission_per_side_per_lot=3.5,
    usd_per_pip_per_lot=10.0,
    pip_value=0.0001
)

# Run backtest
engine = BacktestEngine(config, data_source, api_client, broker)
results = engine.run()

# Save results
reporter = BacktestReporter(output_dir="./results")
reporter.save_results(results, "EURUSD", "H1")
reporter.print_summary(results, "EURUSD", "H1")
```

## Design Principles

1. **API-only signals**: No direct strategy imports - all logic in API
2. **Separation of concerns**: Each module has a single responsibility
3. **Testability**: Pure functions and dependency injection
4. **Determinism**: Same inputs = same outputs
5. **Realistic simulation**: Proper fill model and cost accounting

## Migrating from Old backtest.py

The old `tests/backtest.py` directly imported strategy modules. This new package:

- ✅ Calls HTTP API for signals (no strategy imports)
- ✅ Clean OOP design (not monolithic)
- ✅ Proper separation of concerns
- ✅ Modular and testable
- ✅ Supports both optimized (bar_time) and legacy (data array) modes
- ✅ Import guard test to prevent regressions

To migrate, simply:
1. Start the API server
2. Use this package instead of old backtest.py
3. All strategy parameters now passed via API request

## Troubleshooting

**API connection errors**: Ensure API server is running on the specified URL
```bash
curl http://localhost:8000/health
```

**MT5 data loading errors**: Check MT5 connection and symbol availability

**Import errors**: Ensure you're running from the repo root:
```bash
cd /path/to/volarix4
python -m volarix4_backtest ...
```

## License

Copyright (c) 2026 Volarix Team
