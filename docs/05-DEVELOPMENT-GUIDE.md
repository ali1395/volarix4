# Volarix 4 - Development Guide

## Getting Started

### Prerequisites

- **Python**: 3.8 or higher
- **MetaTrader 5**: Installed and running
- **MT5 Account**: Valid login credentials
- **Operating System**: Windows (MT5 requirement)

### Installation

1. **Clone or Download the Project**:
   ```bash
   cd E:\prs\frx_news_root\volarix4
   ```

2. **Create Virtual Environment** (recommended):
   ```bash
   python -m venv env
   env\Scripts\activate  # Windows
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment**:
   ```bash
   cp .env.example .env
   ```

   Edit `.env`:
   ```bash
   MT5_LOGIN=12345678
   MT5_PASSWORD=yourpassword
   MT5_SERVER=YourBroker-Server
   API_HOST=0.0.0.0
   API_PORT=8000
   DEBUG=false
   ```

5. **Start MetaTrader 5**:
   - Open MT5 terminal
   - Login with your credentials
   - Ensure "Enable automated trading" is checked

6. **Run the API**:
   ```bash
   python scripts/start.py
   ```

   Or directly:
   ```bash
   python volarix4/run.py
   ```

7. **Verify Installation**:
   ```bash
   curl http://localhost:8000/health
   ```

   Should return:
   ```json
   {"status": "healthy", "mt5_connected": true, "version": "4.0.0"}
   ```

## Project Structure

```
volarix4/
├── main.py              # FastAPI application (entry point)
├── config.py            # Configuration management
├── data.py              # MT5 data fetching
├── sr_levels.py         # S/R detection logic
├── rejection.py         # Rejection pattern recognition
├── trade_setup.py       # SL/TP calculation
├── utils.py             # Helper functions
├── logger.py            # Logging system
├── monitor.py           # Performance monitoring
├── start.py             # Startup script
├── test_api.py          # API test suite
├── backtest.py          # Development backtest
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
├── .env                 # Environment variables (gitignored)
├── README.md            # Quick start guide
├── docs/                # Documentation
└── logs/                # Application logs (auto-created)
```

## Development Workflow

### 1. Making Changes

**Typical development flow**:

```bash
# 1. Create a new branch
git checkout -b feature/your-feature

# 2. Make changes to code

# 3. Test individual modules (import and run functions from package)
from volarix4.core import sr_levels      # Test S/R detection
from volarix4.core import rejection      # Test rejection patterns
from volarix4.core import trade_setup    # Test trade setup

# 4. Test API
python tests/test_api.py

# 5. Run backtest
python tests/backtest.py

# 6. Commit changes
git add .
git commit -m "Add feature: your-feature"

# 7. Push to remote
git push origin feature/your-feature
```

### 2. Testing Individual Modules

Each module has built-in test code that runs when executed directly:

**Test S/R Detection**:
```bash
python sr_levels.py
```
Output:
```
Testing sr_levels.py module...
1. Finding swing highs and lows...
Found 8 swing highs and 7 swing lows

2. Detecting S/R levels...
Detected 3 S/R levels:
  SUPPORT: 1.08650 (score: 80.0)
  RESISTANCE: 1.08950 (score: 70.0)
  SUPPORT: 1.08500 (score: 65.0)
```

**Test Rejection Patterns**:
```bash
python rejection.py
```

**Test Trade Setup**:
```bash
python trade_setup.py
```

**Test MT5 Connection**:
```bash
python data.py
```

**Test Logging**:
```bash
python logger.py
```

**Test Monitoring**:
```bash
python monitor.py
```

### 3. Running API Tests

**Full test suite**:
```bash
python tests/test_api.py
```

Tests include:
- Health check endpoint
- Signal generation with valid data
- Invalid request handling
- Multiple symbol testing
- Response time benchmarking
- Volarix 3 compatibility

### 4. Running Backtests

**Development backtest** (not for production):
```bash
python tests/backtest.py
```

Output:
```
Volarix 4 - Development Backtest
=================================

Symbol: EURUSD
Timeframe: H1
Period: 2024-01-01 to 2024-03-31

Fetching data from MT5...
Running bar-by-bar simulation...

Progress: 100% [████████████████████] 2160/2160 bars

Results:
--------
Total Trades: 42
Winning Trades: 27 (64.3%)
Losing Trades: 15 (35.7%)
Total Pips: +185.5
Average Win: +18.2 pips
Average Loss: -10.5 pips
Profit Factor: 1.85
Max Drawdown: -52.3 pips
```

**Important**: This is a simplified backtest for development. For accurate results, use MT5 Strategy Tester with the EA in `mt5_integration/`.

## Configuration Management

### Environment Variables

Create `.env` file (from `.env.example`):

```bash
# MT5 Connection
MT5_LOGIN=12345678
MT5_PASSWORD=yourpassword
MT5_SERVER=YourBroker-Server

# API Settings
API_HOST=0.0.0.0          # 0.0.0.0 = all interfaces, 127.0.0.1 = localhost only
API_PORT=8000
DEBUG=false               # true = detailed logging, false = production mode
```

### Strategy Configuration

Edit `config.py` to tune strategy parameters:

```python
# S/R Detection
SR_CONFIG = {
    "lookback": 50,              # Increase for more historical levels
    "swing_window": 5,           # Decrease for more sensitive swings
    "min_touches": 3,            # Higher = stricter levels
    "cluster_pips": 10.0,        # Wider = fewer, stronger levels
    "min_level_score": 60.0      # Higher = only best levels
}

# Rejection Criteria
REJECTION_CONFIG = {
    "min_wick_body_ratio": 1.5,  # Higher = only strong rejections
    "max_distance_pips": 10.0,   # How close to level must touch be
    "close_position_buy": 0.60,  # Higher = more bullish close required
    "close_position_sell": 0.40, # Lower = more bearish close required
    "lookback_candles": 5        # How many recent candles to check
}

# Risk Management
RISK_CONFIG = {
    "sl_pips_beyond": 10.0,      # SL distance from level
    "tp1_r": 1.0,                # First TP ratio
    "tp2_r": 2.0,                # Second TP ratio
    "tp3_r": 3.0,                # Third TP ratio
    "tp1_percent": 0.40,         # 40% at TP1
    "tp2_percent": 0.40,         # 40% at TP2
    "tp3_percent": 0.20,         # 20% at TP3
}
```

**Testing Configuration Changes**:
```bash
# 1. Edit config.py
# 2. Restart API
python scripts/start.py

# 3. Run backtest to validate
python tests/backtest.py
```

## Adding New Features

### Example: Adding a Trend Filter

**Step 1**: Add trend detection function to `utils.py`:

```python
def detect_trend(df: pd.DataFrame, period: int = 50) -> str:
    """
    Detect trend using simple moving average.

    Args:
        df: DataFrame with OHLC data
        period: MA period

    Returns:
        'UPTREND', 'DOWNTREND', or 'RANGING'
    """
    if len(df) < period:
        return 'RANGING'

    # Calculate SMA
    sma = df['close'].rolling(window=period).mean()
    current_price = df['close'].iloc[-1]
    current_sma = sma.iloc[-1]

    # Determine trend
    if current_price > current_sma * 1.001:  # 0.1% above
        return 'UPTREND'
    elif current_price < current_sma * 0.999:  # 0.1% below
        return 'DOWNTREND'
    else:
        return 'RANGING'
```

**Step 2**: Add configuration to `config.py`:

```python
TREND_FILTER_CONFIG = {
    "enabled": True,
    "period": 50,
    "only_with_trend": True  # Only BUY in uptrend, SELL in downtrend
}
```

**Step 3**: Integrate into signal generation in `main.py`:

```python
# After S/R detection, before rejection search
if TREND_FILTER_CONFIG["enabled"]:
    trend = detect_trend(df, period=TREND_FILTER_CONFIG["period"])
    log_signal_details(logger, "TREND_FILTER", {'trend': trend})

    if TREND_FILTER_CONFIG["only_with_trend"]:
        # Filter rejection search by trend
        if trend == 'UPTREND':
            levels = [l for l in levels if l['type'] == 'support']
        elif trend == 'DOWNTREND':
            levels = [l for l in levels if l['type'] == 'resistance']
```

**Step 4**: Test the change:

```bash
# Test trend detection (import and run from package)
from volarix4.utils import helpers

# Test API with new filter
python tests/test_api.py

# Backtest with trend filter
python tests/backtest.py
```

**Step 5**: Document the change in `docs/03-STRATEGY-LOGIC.md`.

### Example: Adding Volume Confirmation

**Step 1**: Add volume analysis to `rejection.py`:

```python
def has_volume_confirmation(row: pd.Series, df: pd.DataFrame,
                           min_volume_ratio: float = 1.2) -> bool:
    """
    Check if candle has above-average volume.

    Args:
        row: Current candle
        df: Full DataFrame
        min_volume_ratio: Minimum ratio vs 20-bar average

    Returns:
        True if volume is above average
    """
    if len(df) < 20:
        return True  # Not enough data, skip filter

    avg_volume = df['volume'].tail(20).mean()
    current_volume = row['volume']

    return current_volume >= (avg_volume * min_volume_ratio)
```

**Step 2**: Update `find_rejection_candle()` to use it:

```python
def find_rejection_candle(df: pd.DataFrame, levels: List[Dict],
                         lookback: int = 5,
                         pip_value: float = 0.0001,
                         volume_filter: bool = False) -> Optional[Dict]:
    # ... existing code ...

    for idx in range(len(recent_candles) - 1, -1, -1):
        candle = recent_candles.iloc[idx]

        # Check volume if filter enabled
        if volume_filter:
            if not has_volume_confirmation(candle, df):
                continue  # Skip low volume candles

        # ... rest of rejection logic ...
```

## Debugging

### Enable Debug Logging

**Method 1**: Environment variable:
```bash
DEBUG=true python volarix4/run.py
```

**Method 2**: Change log level in code:
```python
# In logger.py or main.py
logger = setup_logger("volarix4", level="DEBUG")
```

**Debug output**:
```
2024-01-15 10:30:45 - DEBUG - Request Body: {"symbol":"EURUSD"...}
2024-01-15 10:30:45 - DEBUG - Swing highs found at indices: [12, 25, 38, 45]
2024-01-15 10:30:45 - DEBUG - Clustering 8 support levels...
2024-01-15 10:30:45 - DEBUG - Checking candle at index 49 for rejection...
```

### Common Issues

**Issue**: `MT5 connection failed`
```
Solution:
1. Ensure MT5 terminal is running
2. Check credentials in .env
3. Verify MT5 allows API connections (Tools > Options > Expert Advisors)
4. Try manual login in MT5 first
```

**Issue**: `No S/R levels detected`
```
Solution:
1. Lower min_level_score threshold (e.g., 40 instead of 60)
2. Increase lookback period (e.g., 100 bars)
3. Check if data has enough history
4. Verify data quality (no gaps, valid OHLCV)
```

**Issue**: `Always returns HOLD`
```
Solution:
1. Check session filter (are you in London/NY session?)
2. Lower rejection criteria (min_wick_body_ratio = 1.2)
3. Increase max_distance_pips (allow touching further from level)
4. Review logs for specific rejection reasons
```

### Logging Best Practices

```python
# Use appropriate log levels
logger.debug("Detailed debugging info")  # Development only
logger.info("Normal operation info")     # General flow
logger.warning("Unexpected but handled")  # Warnings
logger.error("Error occurred", exc_info=True)  # Errors with stack trace

# Use structured logging
log_signal_details(logger, "STEP_NAME", {
    'key1': value1,
    'key2': value2
})

# Log at key decision points
logger.info(f"Filtering levels: {len(levels)} → {len(filtered)} after score filter")
```

## Testing

### Unit Testing (Manual)

Each module has test code at the bottom:

```python
if __name__ == "__main__":
    # Test code here
    print("Testing module...")
```

Run with:
```bash
python module_name.py
```

### Integration Testing

Use `test_api.py`:

```python
# Add your own tests
def test_custom_scenario():
    """Test custom trading scenario."""
    # Prepare test data
    bars = generate_test_bars_with_rejection()

    # Send request
    response = requests.post(f"{API_URL}/signal", json={
        "symbol": "EURUSD",
        "timeframe": "H1",
        "data": bars
    })

    # Assert response
    assert response.status_code == 200
    signal = response.json()
    assert signal['signal'] == 'BUY'
    assert signal['confidence'] > 0.5

    print("✓ Custom scenario test passed")
```

### Backtest Validation

Before deploying changes, run backtest:

```bash
python tests/backtest.py
```

Compare results to baseline:
- Win rate should be 50-65%
- Profit factor should be > 1.3
- Max drawdown should be reasonable

### Parity Testing

**CRITICAL**: Always run parity tests before deploying changes to ensure backtest and API remain synchronized.

#### Running Parity Tests

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run all parity tests
python -m pytest tests/test_backtest_api_parity.py -v
```

**Expected Output**:
```
tests/test_backtest_api_parity.py::test_backtest_api_parity[trade_accepted] PASSED
tests/test_backtest_api_parity.py::test_backtest_api_parity[rejected_session] PASSED
tests/test_backtest_api_parity.py::test_backtest_api_parity[rejected_confidence] PASSED
tests/test_backtest_api_parity.py::test_backtest_api_parity[rejected_insufficient_edge] PASSED
tests/test_backtest_api_parity.py::test_parameter_defaults_match PASSED
tests/test_backtest_api_parity.py::test_session_hours_unchanged PASSED
tests/test_backtest_api_parity.py::test_ema_periods_unchanged PASSED
tests/test_backtest_api_parity.py::test_cost_model_formula_unchanged PASSED

======================= 8 passed in 2.34s =======================
```

#### What Parity Tests Prevent

❌ **Bar indexing changes** (forming bar inclusion at index 0)
❌ **Session hour changes** (London 3-11, NY 8-22 EST)
❌ **EMA period changes** (20/50 periods)
❌ **Cost model changes** (formula or defaults)
❌ **Parameter default changes** (min_confidence, min_edge, etc.)
❌ **Filter order changes** (pipeline sequence)

#### When Tests Fail

If parity tests fail:

1. **If bug**: Fix the code to match expected behavior
2. **If intentional change**: Update fixtures and validation tests
3. **Document change**: Update `docs/PARITY_TESTS.md` and `docs/BACKTEST_PARITY.md`

#### Adding New Test Fixtures

To create a new parity test fixture:

```bash
# 1. Extract bars from a specific scenario using MT5
python tests/extract_bars_from_mt5.py

# 2. Run backtest on those bars to get expected output
python tests/backtest.py --single-test

# 3. Call API with same bars to get actual output
curl -X POST http://localhost:8000/signal -d @test_bars.json

# 4. Create fixture JSON combining bars + expected output
# See tests/fixtures/*.json for examples

# 5. Add fixture to test_backtest_api_parity.py parametrize list
```

**See**: `docs/PARITY_TESTS.md` for comprehensive parity testing documentation.

## Deployment

### Local Deployment

**Option 1**: Direct execution:
```bash
python volarix4/run.py
```

**Option 2**: Using uvicorn:
```bash
uvicorn volarix4.api.main:app --host 0.0.0.0 --port 8000
```

**Option 3**: With auto-reload (development):
```bash
uvicorn volarix4.api.main:app --reload --host 127.0.0.1 --port 8000
```

### Production Deployment

**Step 1**: Set production config:
```bash
# .env
DEBUG=false
API_HOST=0.0.0.0
API_PORT=8000
```

**Step 2**: Run with production server:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
```

**Step 3**: Add process manager (e.g., systemd):

Create `/etc/systemd/system/volarix4.service`:
```ini
[Unit]
Description=Volarix 4 Trading API
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/volarix4
Environment="PATH=/path/to/volarix4/env/bin"
ExecStart=/path/to/volarix4/env/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable volarix4
sudo systemctl start volarix4
sudo systemctl status volarix4
```

**Step 4**: Add reverse proxy (nginx):

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Docker Deployment (Future)

Create `Dockerfile`:
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t volarix4 .
docker run -p 8000:8000 --env-file .env volarix4
```

## Contributing

### Code Style

Follow PEP 8 guidelines:

```bash
# Install linter
pip install flake8

# Check code
flake8 main.py

# Auto-format
pip install black
black main.py
```

### Documentation

When adding features:
1. Update inline code comments
2. Update docstrings
3. Update relevant docs/ files
4. Add examples to README.md

### Pull Requests

1. Create feature branch
2. Make changes
3. Test thoroughly
4. Update documentation
5. Submit PR with clear description

## Performance Optimization

### Profiling

```python
import cProfile
import pstats

# Profile signal generation
profiler = cProfile.Profile()
profiler.enable()

# Run signal generation
signal = generate_signal(request)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 slowest functions
```

### Caching

Add caching for S/R levels:

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def detect_sr_levels_cached(df_hash, min_score, pip_value):
    # Detection logic
    return levels
```

### Async Processing

For multiple symbols:

```python
import asyncio
import aiohttp

async def get_signals_async(symbols):
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_signal(session, symbol)
            for symbol in symbols
        ]
        return await asyncio.gather(*tasks)

# Usage
symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
signals = asyncio.run(get_signals_async(symbols))
```

## Troubleshooting

### MT5 Connection Issues

```python
# Test MT5 connection
import MetaTrader5 as mt5

if not mt5.initialize():
    print(f"Initialize failed: {mt5.last_error()}")

if not mt5.login(login, password, server):
    print(f"Login failed: {mt5.last_error()}")

# Check terminal info
info = mt5.terminal_info()
print(f"Connected: {info is not None}")
print(f"Build: {info.build if info else 'N/A'}")
```

### API Not Responding

```bash
# Check if running
curl http://localhost:8000/health

# Check logs
tail -f logs/volarix4_*.log

# Check process
netstat -ano | findstr :8000  # Windows
lsof -i :8000                  # Linux/Mac
```

### Memory Leaks

```python
# Monitor memory usage
import psutil
import os

process = psutil.Process(os.getpid())
print(f"Memory: {process.memory_info().rss / 1024 / 1024:.2f} MB")

# Profile memory
from memory_profiler import profile

@profile
def generate_signal(request):
    # Function code
```

## Additional Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **MT5 Python Docs**: https://www.mql5.com/en/docs/python_metatrader5
- **Pandas Docs**: https://pandas.pydata.org/docs/
- **Pydantic Docs**: https://docs.pydantic.dev/

## Support

For issues or questions:
1. Check documentation in `docs/`
2. Review logs in `logs/`
3. Search existing GitHub issues
4. Create new issue with detailed description and logs
