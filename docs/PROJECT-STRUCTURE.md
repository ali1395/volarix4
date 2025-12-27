# Volarix 4 - Project Structure

## Directory Layout

```
volarix4/
├── volarix4/                  # Main package directory
│   ├── __init__.py           # Package initialization
│   ├── config.py             # Configuration management
│   │
│   ├── api/                  # API layer
│   │   ├── __init__.py      # API package initialization
│   │   └── main.py          # FastAPI application and routes
│   │
│   ├── core/                 # Core trading logic
│   │   ├── __init__.py      # Core package initialization
│   │   ├── data.py          # MT5 data fetching
│   │   ├── sr_levels.py     # Support/Resistance detection
│   │   ├── rejection.py     # Rejection pattern recognition
│   │   └── trade_setup.py   # SL/TP calculation
│   │
│   └── utils/                # Utility modules
│       ├── __init__.py      # Utils package initialization
│       ├── helpers.py       # Helper functions (pip calculations, etc.)
│       ├── logger.py        # Logging system
│       └── monitor.py       # Performance monitoring
│
├── tests/                    # Test files
│   ├── __init__.py
│   ├── test_api.py          # API integration tests
│   └── backtest.py          # Development backtest
│
├── scripts/                  # Utility scripts
│   └── start.py             # Startup script with banner
│
├── docs/                     # Documentation
│   ├── README.md            # Documentation hub
│   ├── 01-PROJECT-OVERVIEW.md
│   ├── 02-ARCHITECTURE.md
│   ├── 03-STRATEGY-LOGIC.md
│   ├── 04-API-REFERENCE.md
│   └── 05-DEVELOPMENT-GUIDE.md
│
├── mt5_integration/          # MT5 Expert Advisor integration
│   ├── README_MT5.md
│   ├── volarix4.mq5
│   ├── volarix.cpp
│   └── volarix4_bridge.cpp
│
├── logs/                     # Application logs (auto-created)
│   └── volarix4_YYYY-MM-DD.log
│
├── run.py                    # Main entry point
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
├── .env                      # Environment variables (gitignored)
├── PROJECT-STRUCTURE.md      # This file
└── README.md                 # Quick start guide
```

## Package Organization

### Main Package (`volarix4/`)

The core application code is organized as a Python package:

- **`__init__.py`**: Exports main configuration variables
- **`config.py`**: Centralized configuration (Strategy parameters, API settings, MT5 credentials)

### API Layer (`volarix4/api/`)

HTTP API implementation using FastAPI:

- **`main.py`**: FastAPI application, route handlers, middleware, exception handlers

**Key Functions**:
- `create_app()`: Factory function that creates and configures the FastAPI app
- `generate_signal()`: POST /signal endpoint handler
- `health_check()`: GET /health endpoint handler
- `root()`: GET / endpoint handler

### Core Logic (`volarix4/core/`)

Trading strategy implementation:

- **`data.py`**: MT5 connection and data fetching
  - `connect_mt5()`: Establish MT5 connection
  - `fetch_ohlc()`: Retrieve OHLCV bars
  - `is_valid_session()`: Session validation

- **`sr_levels.py`**: Support/Resistance level detection
  - `find_swing_highs()`: Identify swing highs
  - `find_swing_lows()`: Identify swing lows
  - `cluster_levels()`: Cluster nearby levels
  - `detect_sr_levels()`: Main S/R detection function

- **`rejection.py`**: Rejection candle pattern recognition
  - `is_support_rejection()`: Check for support bounce
  - `is_resistance_rejection()`: Check for resistance rejection
  - `find_rejection_candle()`: Main rejection search function

- **`trade_setup.py`**: Trade entry, SL, and TP calculation
  - `calculate_sl_tp()`: Calculate stop-loss and take-profits
  - `calculate_trade_setup()`: Main trade setup function

### Utilities (`volarix4/utils/`)

Helper functions and infrastructure:

- **`helpers.py`**: Utility functions
  - `calculate_pip_value()`: Get pip size for symbol
  - `pips_to_price()`: Convert pips to price
  - `price_to_pips()`: Convert price to pips
  - `format_price()`: Format prices for display
  - `get_current_est_hour()`: Get EST timezone hour

- **`logger.py`**: Structured logging system
  - `setup_logger()`: Configure logger
  - `log_signal_details()`: Log structured signal data

- **`monitor.py`**: Performance monitoring
  - `PerformanceMonitor`: Metrics tracking class
  - `monitor`: Global monitor instance

## Entry Points

### 1. `run.py` (Recommended)

Simple entry point for starting the API:

```bash
python run.py
```

### 2. `scripts/start.py`

Alternative with ASCII banner:

```bash
python scripts/start.py
```

### 3. Direct uvicorn

For advanced users:

```bash
uvicorn volarix4.api.main:app --host 0.0.0.0 --port 8000
```

## Import Patterns

### Importing from the package

**From outside the package**:
```python
from volarix4.core.data import fetch_ohlc
from volarix4.core.sr_levels import detect_sr_levels
from volarix4.utils.helpers import calculate_pip_value
from volarix4.config import SR_CONFIG
```

**Within the package**:
```python
# In volarix4/api/main.py
from volarix4.core.data import is_valid_session
from volarix4.utils.logger import setup_logger
```

## Configuration Files

### `.env` (Environment Variables)

```bash
# MT5 Connection
MT5_LOGIN=12345678
MT5_PASSWORD=yourpassword
MT5_SERVER=YourBroker-Server

# API Settings
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false
```

### `volarix4/config.py` (Strategy Configuration)

```python
# S/R Detection
SR_CONFIG = {
    "lookback": 50,
    "swing_window": 5,
    "min_touches": 3,
    "cluster_pips": 10.0,
    "min_level_score": 60.0
}

# Rejection Criteria
REJECTION_CONFIG = {
    "min_wick_body_ratio": 1.5,
    "max_distance_pips": 10.0,
    "close_position_buy": 0.60,
    "close_position_sell": 0.40,
    "lookback_candles": 5
}

# Risk Management
RISK_CONFIG = {
    "sl_pips_beyond": 10.0,
    "tp1_r": 1.0,
    "tp2_r": 2.0,
    "tp3_r": 3.0,
    "tp1_percent": 0.40,
    "tp2_percent": 0.40,
    "tp3_percent": 0.20
}
```

## Testing

### API Tests

```bash
# Make sure API is running first
python run.py

# In another terminal:
python tests/test_api.py
```

### Development Backtest

```bash
python tests/backtest.py
```

### Individual Module Tests

Each core module can be tested independently:

```bash
python -m volarix4.core.sr_levels
python -m volarix4.core.rejection
python -m volarix4.core.trade_setup
python -m volarix4.utils.helpers
python -m volarix4.utils.logger
python -m volarix4.utils.monitor
```

## Development Workflow

### 1. Making Changes

```bash
# Edit files in volarix4/ package
vim volarix4/core/sr_levels.py

# Test the module
python -m volarix4.core.sr_levels

# Restart API to see changes (if not using reload mode)
python run.py
```

### 2. Adding New Features

**Example: Adding a new utility function**

1. Add function to `volarix4/utils/helpers.py`:
```python
def new_utility_function():
    pass
```

2. Export from `volarix4/utils/__init__.py`:
```python
from volarix4.utils.helpers import new_utility_function

__all__ = [..., "new_utility_function"]
```

3. Use in other modules:
```python
from volarix4.utils import new_utility_function
```

### 3. Adding New Modules

1. Create file in appropriate package:
```bash
touch volarix4/core/new_module.py
```

2. Implement functionality

3. Export from package `__init__.py`:
```python
# In volarix4/core/__init__.py
from volarix4.core.new_module import new_function

__all__ = [..., "new_function"]
```

## Benefits of Package Structure

### 1. **Clarity**
- Clear separation of concerns (API, core logic, utilities)
- Easy to find specific functionality
- Obvious where new code should go

### 2. **Maintainability**
- Modules are logically grouped
- Easy to refactor without breaking imports
- Clear dependencies between components

### 3. **Testability**
- Each package can be tested independently
- Easy to mock dependencies
- Clear import paths in tests

### 4. **Scalability**
- Easy to add new packages (e.g., `volarix4/backtest/`)
- Can split large modules without breaking imports
- Supports future growth (web UI, database layer, etc.)

### 5. **Distribution**
- Can be packaged and distributed via pip
- Can be imported by other projects
- Supports installation in development mode: `pip install -e .`

## Migration from Old Structure

### Old Structure (Root-level files)
```
volarix4/
├── main.py
├── config.py
├── data.py
├── sr_levels.py
├── rejection.py
├── trade_setup.py
├── utils.py
├── logger.py
├── monitor.py
├── test_api.py
└── backtest.py
```

### New Structure (Package organization)
```
volarix4/
├── volarix4/
│   ├── api/main.py          # main.py moved here
│   ├── config.py            # stays at package root
│   ├── core/                # trading logic grouped
│   │   ├── data.py
│   │   ├── sr_levels.py
│   │   ├── rejection.py
│   │   └── trade_setup.py
│   └── utils/               # utilities grouped
│       ├── helpers.py       # utils.py renamed
│       ├── logger.py
│       └── monitor.py
├── tests/                   # tests separated
│   ├── test_api.py
│   └── backtest.py
└── run.py                   # new entry point
```

### Import Changes

**Old imports**:
```python
from data import fetch_ohlc
from sr_levels import detect_sr_levels
from utils import calculate_pip_value
```

**New imports**:
```python
from volarix4.core.data import fetch_ohlc
from volarix4.core.sr_levels import detect_sr_levels
from volarix4.utils.helpers import calculate_pip_value
```

## Future Improvements

Potential package additions:

```
volarix4/
├── volarix4/
│   ├── api/
│   ├── core/
│   ├── utils/
│   ├── backtest/           # Future: Full backtest engine
│   ├── database/           # Future: Trade storage
│   ├── notifications/      # Future: Alert system
│   └── ui/                 # Future: Web dashboard
├── tests/
└── docs/
```

## Getting Help

- **Documentation**: See `docs/` folder for comprehensive guides
- **Module help**: Use Python's help() function:
  ```python
  from volarix4.core import sr_levels
  help(sr_levels.detect_sr_levels)
  ```
- **Examples**: Check `tests/` for usage examples
