# Volarix 4 Backtest

API-based backtesting engine for Volarix 4 strategy.

## Overview

This package provides a clean, OOP-based backtesting framework that:

- **API-only signals**: ALL signal generation goes through the HTTP `/signal` endpoint (no direct strategy imports)
- **JSON configuration**: All parameters set in config file (no complex CLI args)
- **Year-based walk-forward**: Train on N previous years, test on target year
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

## Quick Start

### 1. Start API Server
```bash
cd E:\prs\frx_news_root\volarix4
python run.py
```

### 2. Run Year-Based Walk-Forward Backtest

**Using JSON config (RECOMMENDED):**
```bash
# Edit backtest_config.json to set your parameters
python -m volarix4_backtest --config backtest_config.json
```

Example `backtest_config.json`:
```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "test_years": [2023, 2024, 2025],
  "train_years_lookback": 2,
  "min_confidence": 0.7,
  "spread_pips": 1.5,
  "lot_size": 0.01,
  "verbose": false
}
```

This will:
- Test 2023 (train on 2021-2022)
- Test 2024 (train on 2022-2023)
- Test 2025 (train on 2023-2024)

### 3. Run Simple Single-Period Backtest

```bash
# Use simple config
python -m volarix4_backtest --config backtest_config_simple.json
```

Or legacy CLI args:
```bash
python -m volarix4_backtest --symbol EURUSD --timeframe H1 --bars 5000 --verbose
```

## Configuration File Format

### Full Example (Year-Based Walk-Forward)
```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",

  "test_years": [2023, 2024, 2025],
  "train_years_lookback": 2,

  "api_url": "http://localhost:8000",
  "api_timeout": 30.0,
  "api_max_retries": 3,
  "use_optimized_mode": true,
  "lookback_bars": 400,

  "min_confidence": 0.7,
  "broken_level_cooldown_hours": 24.0,
  "broken_level_break_pips": 15.0,
  "min_edge_pips": 2.0,

  "spread_pips": 1.5,
  "slippage_pips": 0.5,
  "commission_per_side_per_lot": 3.5,
  "usd_per_pip_per_lot": 10.0,
  "lot_size": 0.01,

  "initial_balance_usd": 10000.0,
  "risk_percent_per_trade": 1.0,

  "fill_at": "next_open",
  "warmup_bars": 200,

  "output_dir": "./backtest_results",
  "save_trades_csv": true,
  "save_equity_curve": true,
  "verbose": false
}
```

### Simple Example (Single Period)
```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "bars": 5000,
  "min_confidence": 0.7,
  "verbose": true
}
```

## Configuration Parameters

### Trading Setup
- `symbol`: Trading pair (e.g., "EURUSD")
- `timeframe`: Timeframe ("H1", "M15", "D1", etc.)

### Year-Based Walk-Forward
- `test_years`: Array of years to test (e.g., `[2023, 2024, 2025]`)
- `train_years_lookback`: Number of years to train on before each test year (default: 2)

### Legacy Date Range (single-period only)
- `start_date`: Start date "YYYY-MM-DD"
- `end_date`: End date "YYYY-MM-DD"
- `bars`: Number of recent bars (alternative to dates)

### API Configuration
- `api_url`: API base URL (default: "http://localhost:8000")
- `api_timeout`: Timeout in seconds (default: 30.0)
- `api_max_retries`: Max retries (default: 3)
- `use_optimized_mode`: Use bar_time mode (default: true)
- `lookback_bars`: Bars for signal generation (default: 400)

### Parity Parameters
- `min_confidence`: Min confidence threshold
- `broken_level_cooldown_hours`: Cooldown period for broken levels
- `broken_level_break_pips`: Pips threshold for level breakage
- `min_edge_pips`: Minimum edge after costs

### Cost Model
- `spread_pips`: Spread cost (default: 1.5)
- `slippage_pips`: Slippage per execution (default: 0.5)
- `commission_per_side_per_lot`: Commission in USD (default: 3.5)
- `usd_per_pip_per_lot`: USD per pip per lot (default: 10.0)
- `lot_size`: Position size in lots (default: 0.01)

### Risk Management
- `initial_balance_usd`: Starting balance (default: 10000.0)
- `risk_percent_per_trade`: Risk % per trade (default: 1.0)

### Execution
- `fill_at`: "next_open" (no peeking) or "signal_close" (default: "next_open")
- `warmup_bars`: Min bars before first signal (default: 200)

### Output
- `output_dir`: Results directory (default: "./backtest_results")
- `save_trades_csv`: Save trades CSV (default: true)
- `save_equity_curve`: Save equity curve CSV (default: true)
- `verbose`: Verbose logging (default: false)

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

### Year-Based Walk-Forward Testing

1. **Create/edit config file** (`backtest_config.json`):
   ```json
   {
     "symbol": "EURUSD",
     "timeframe": "H1",
     "test_years": [2023, 2024, 2025],
     "train_years_lookback": 2,
     "min_confidence": 0.7,
     "verbose": true
   }
   ```

2. **Start API server**:
   ```bash
   cd E:\prs\frx_news_root\volarix4
   python run.py
   ```

3. **Run walk-forward test**:
   ```bash
   python -m volarix4_backtest --config backtest_config.json
   ```

4. **View results**:
   ```
   ======================================================================
   WALK-FORWARD TESTING SUMMARY
   ======================================================================
   Test Years: [2023, 2024, 2025]
   Train Years Lookback: 2

   RESULTS BY YEAR
   ----------------------------------------------------------------------
   2023:
     Trades: 45
     Win Rate: 62.22%
     Net Profit: $1,234.56
     Return: 12.35%
   2024:
     Trades: 38
     Win Rate: 57.89%
     Net Profit: $987.65
     Return: 9.88%
   2025:
     Trades: 42
     Win Rate: 64.29%
     Net Profit: $1,456.78
     Return: 14.57%

   AGGREGATE METRICS (All Years)
   ----------------------------------------------------------------------
   Total Years Tested: 3
   Total Trades: 125
   Avg Trades/Year: 41.7
   Win Rate: 61.60%
   Profit Factor: 1.78
   Aggregate Net Profit: $3,678.99
   Aggregate Return: 36.79%
   ======================================================================
   ```

## Programmatic Usage

### Year-Based Walk-Forward
```python
from volarix4_backtest import (
    BacktestConfig,
    BarDataSource,
    SignalApiClient,
    BrokerSimulator,
    WalkForwardEngine
)

# Load config from JSON
config = BacktestConfig.from_json("backtest_config.json")

# Or create programmatically
config = BacktestConfig(
    symbol="EURUSD",
    timeframe="H1",
    test_years=[2023, 2024, 2025],
    train_years_lookback=2,
    min_confidence=0.7,
    verbose=True
)

# Create components
data_source = BarDataSource(source="mt5", symbol="EURUSD", timeframe="H1")
api_client = SignalApiClient(base_url="http://localhost:8000")
broker = BrokerSimulator(
    spread_pips=1.5, slippage_pips=0.5, commission_per_side_per_lot=3.5,
    usd_per_pip_per_lot=10.0, pip_value=0.0001
)

# Run walk-forward
engine = WalkForwardEngine(config, data_source, api_client, broker)
results = engine.run()

# Results structure:
# results = {
#     "by_year": {
#         2023: {...},  # Results for 2023
#         2024: {...},  # Results for 2024
#         2025: {...}   # Results for 2025
#     },
#     "aggregate": {
#         "total_trades": 125,
#         "win_rate": 0.616,
#         "aggregate_net_profit": 3678.99,
#         ...
#     }
# }
```

### Single-Period Backtest
```python
from volarix4_backtest import BacktestConfig, BacktestEngine, ...

config = BacktestConfig(symbol="EURUSD", timeframe="H1", bars=5000)
data_source = BarDataSource(source="mt5", symbol="EURUSD", timeframe="H1", bars=5000)
data_source.load()

engine = BacktestEngine(config, data_source, api_client, broker)
results = engine.run()
```

## Design Principles

1. **API-only signals**: No direct strategy imports - all logic in API
2. **Separation of concerns**: Each module has a single responsibility
3. **Testability**: Pure functions and dependency injection
4. **Determinism**: Same inputs = same outputs
5. **Realistic simulation**: Proper fill model and cost accounting

## Year-Based Walk-Forward Testing

### How It Works

When you set `test_years` in the config, the backtest automatically switches to walk-forward mode:

```json
{
  "test_years": [2023, 2024, 2025],
  "train_years_lookback": 2
}
```

**Execution:**
- **Test 2023**: Train on 2021-2022 data, test on 2023 data
- **Test 2024**: Train on 2022-2023 data, test on 2024 data
- **Test 2025**: Train on 2023-2024 data, test on 2025 data

**Note**: Currently, the "training" phase doesn't optimize parameters - it just uses the configured parameters on the test period. If you want parameter optimization, you can extend `WalkForwardEngine._run_test_period()` to run parameter sweeps on training data.

### Benefits

1. **Out-of-sample testing**: Each year tested with parameters from past data
2. **Realistic performance**: Simulates forward testing without look-ahead bias
3. **Robustness validation**: Consistent performance across years indicates robust strategy
4. **Overfitting detection**: Large train/test performance gap indicates overfitting

## Migrating from Old backtest.py

The old `tests/backtest.py` directly imported strategy modules. This new package:

- ✅ **JSON config files** (no complex CLI args)
- ✅ **Year-based walk-forward** (train on past, test on target)
- ✅ Calls HTTP API for signals (no strategy imports)
- ✅ Clean OOP design (not monolithic)
- ✅ Proper separation of concerns
- ✅ Modular and testable
- ✅ Import guard test to prevent regressions

To migrate:
1. Create `backtest_config.json` with your parameters
2. Start the API server
3. Run: `python -m volarix4_backtest --config backtest_config.json`

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
