# Volarix 4 - S/R Bounce Trading API

A minimal, production-ready REST API for generating trading signals based on Support/Resistance bounce patterns. Built with FastAPI and MetaTrader 5.

## Features

- **Pure S/R Strategy**: No machine learning, just proven price action
- **Volarix 3 Compatible**: Drop-in replacement with same API interface
- **10-Stage Pipeline**: Bar Validation → Session Filter → Trend Filter → S/R Detection → Broken Level Filter → Rejection Search → Confidence Filter → Trend Alignment → Signal Cooldown → Min Edge Filter
- **Session Filtered**: Only trades during London (3-11am EST) and NY (8am-4pm EST) sessions
- **Risk Management**: Automated SL/TP calculation with 1R/2R/3R targets
- **Backtest-API Parity**: Comprehensive test suite ensures backtest results match live trading

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure MT5 Credentials

```bash
cp .env.example .env
# Edit .env with your MT5 login, password, and server
```

Example `.env`:
```bash
MT5_LOGIN=12345678
MT5_PASSWORD=yourpassword
MT5_SERVER=YourBroker-Server
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false
```

### 3. Start the API

```bash
python run.py
```

Or alternatively:
```bash
python scripts/start.py
```

The API will start on `http://localhost:8000`

### 4. MT5 Integration (Optional - For Automated Trading)

To connect MT5 to the API for automated trading:

1. **Compile the C++ DLL Bridge:**
   - Open `mt5_integration/volarix4_bridge.cpp` in Visual Studio
   - Build as `Volarix4Bridge.dll` (x64, Release)
   - Copy to `[MT5 Data Folder]\MQL5\Libraries\`

2. **Deploy the Expert Advisor:**
   - Copy `mt5_integration/volarix4.mq5` to `[MT5 Data Folder]\MQL5\Experts\`
   - In MT5: Tools → Options → Expert Advisors → Enable "Allow DLL imports"

3. **Run the EA:**
   - Attach volarix4 EA to a chart
   - Configure parameters (Symbol, Timeframe, Risk%)
   - Enable AutoTrading

**See [mt5_integration/README_MT5.md](../mt5_integration/README_MT5.md) for detailed setup instructions.**

**⚠️ CRITICAL FIX (Dec 2025)**: The DLL bridge requires `#pragma pack(1)` and `long long timestamp` to avoid struct alignment issues. The current code includes these fixes - do not modify the struct definition without testing!

## API Endpoints

### POST /signal

Generate trading signal for a symbol/timeframe.

**Request:**
```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "bars": 400
}
```

**Response:**
```json
{
  "signal": "BUY",
  "confidence": 0.75,
  "entry": 1.08520,
  "sl": 1.08390,
  "tp1": 1.08650,
  "tp2": 1.08780,
  "tp3": 1.08910,
  "tp1_percent": 0.4,
  "tp2_percent": 0.4,
  "tp3_percent": 0.2,
  "reason": "Support bounce at 1.08500, score 85.0"
}
```

**Signal Types:**
- `BUY`: Support bounce detected
- `SELL`: Resistance rejection detected
- `HOLD`: No valid setup found

### GET /health

Check API and MT5 connection status.

**Response:**
```json
{
  "status": "healthy",
  "mt5_connected": true,
  "version": "4.0.0"
}
```

### GET /docs

Interactive API documentation (Swagger UI).

## Testing

### Using cURL

```bash
curl -X POST http://localhost:8000/signal \
  -H "Content-Type: application/json" \
  -d '{"symbol":"EURUSD","timeframe":"H1","bars":400}'
```

### Using Python

```python
import requests

response = requests.post(
    "http://localhost:8000/signal",
    json={
        "symbol": "EURUSD",
        "timeframe": "H1",
        "bars": 400
    }
)

signal = response.json()
print(f"Signal: {signal['signal']}")
print(f"Entry: {signal['entry']}")
print(f"SL: {signal['sl']}")
print(f"Reason: {signal['reason']}")
```

## Strategy Details

### S/R Level Detection
- Identifies swing highs/lows using 5-bar window
- Clusters levels within 10 pips
- Requires minimum 3 touches
- Scores levels based on touches, recency, and rejection strength

### Rejection Criteria
- **Support Bounce (BUY)**:
  - Low touches support level (within 10 pips)
  - Wick/body ratio > 1.5
  - Close in top 40% of candle

- **Resistance Rejection (SELL)**:
  - High touches resistance level (within 10 pips)
  - Wick/body ratio > 1.5
  - Close in bottom 40% of candle

### Risk Management
- **SL**: 10 pips beyond S/R level
- **TP1**: 1R (40% position)
- **TP2**: 2R (40% position)
- **TP3**: 3R (20% position)

### Advanced Filters

- **Trend Filter**: EMA 20/50 crossover (allows counter-trend if confidence >= 0.75)
- **Broken Level Filter**: 48-hour cooldown on broken S/R levels (15 pip breach threshold)
- **Confidence Filter**: Minimum 0.60 confidence threshold (balances quality vs quantity)
- **Signal Cooldown**: 2-hour delay between signals per symbol (prevents over-trading)
- **Min Edge Filter**: Requires 4.0 pips profit after all costs (spread + slippage + commission)

**Default Costs**:
- Spread: 1.0 pips
- Slippage: 0.5 pips (one-way)
- Commission: $7/lot/side
- Min Edge: 4.0 pips

See `docs/03-STRATEGY-LOGIC.md` for detailed filter documentation.

## Configuration

Edit `config.py` to adjust strategy parameters:

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

## Project Structure

```
volarix4/
├── volarix4/                # Main package
│   ├── api/                # API layer (FastAPI)
│   ├── core/               # Core trading logic
│   ├── utils/              # Utilities (logger, monitor, helpers)
│   └── config.py           # Configuration
├── tests/                   # Test files
├── scripts/                 # Utility scripts
├── docs/                    # Documentation
├── mt5_integration/         # MT5 Expert Advisor
├── run.py                   # Main entry point
├── requirements.txt         # Dependencies
├── .env.example             # Environment template
├── PROJECT-STRUCTURE.md     # Detailed structure guide
└── README.md               # This file
```

**See [PROJECT-STRUCTURE.md](PROJECT-STRUCTURE.md) for detailed package organization.**

## Testing & Validation

### Run Test Suite

Comprehensive API testing:

```bash
python tests/test_api.py
```

Tests include:
- Health check endpoint
- Signal generation with valid/invalid inputs
- Volarix 3 compatibility verification
- Multiple symbol testing
- Response time performance

### Parity Tests

Ensure backtest and API remain synchronized:

```bash
# Run parity tests
python -m pytest tests/test_backtest_api_parity.py -v
```

These tests will **FAIL** if:
- Bar indexing changes (forming bar inclusion)
- Session hours change (London/NY times)
- EMA periods change (20/50)
- Cost model formula changes
- Filter order changes
- Parameter defaults change

**Always run parity tests before committing changes to filters or parameters.**

See `docs/PARITY_TESTS.md` for details.

### Development Backtest

Run realistic bar-by-bar backtest:

```bash
python tests/backtest.py
```

**⚠ IMPORTANT NOTE**: This backtest is for development validation only. Final backtesting should be done using a MetaTrader 5 Expert Advisor for accurate results with real broker conditions, spreads, and slippage.

The development backtest provides:
- Realistic SL/TP management
- No look-ahead bias
- Bar-by-bar walk-forward simulation
- Performance statistics (win rate, profit factor, etc.)

### Performance Monitoring

View API performance stats:

```python
from monitor import monitor

# After running some requests
monitor.print_stats()
```

Tracks:
- Request count and success rate
- Response times (avg/min/max)
- Signal distribution
- Top symbols requested

## Requirements

- Python 3.8+
- MetaTrader 5 terminal (must be running)
- MT5 account with valid credentials

## Troubleshooting

### MT5 Connection Failed
- Ensure MT5 terminal is running
- Verify credentials in `.env` are correct
- Check that your MT5 account allows API access

### MT5 DLL Integration Issues

**Wrong dates (1970, 1963, 2003) or corrupted data:**
- Struct alignment mismatch - ensure `#pragma pack(1)` in C++
- Rebuild DLL after any struct changes
- Restart MT5 to unload old DLL from memory

**No TP/SL set on trades:**
- Ensure MQ5 is parsing `entry`, `sl`, and `tp2` from API response
- Check `request.tp = tp2;` is set (line 351 in volarix4.mq5)
- Verify API is returning non-zero TP values

**DLL not loading:**
- Check DLL is in `[MT5 Data Folder]\MQL5\Libraries\Volarix4Bridge.dll`
- Enable "Allow DLL imports" in MT5 Options
- Compile for x64 architecture (not x86)
- Check debug log: `E:\Volarix4Bridge_Debug.txt`

**Non-deterministic trades (different results each run):**
- Memory corruption from struct mismatch
- Verify `OHLCVBar` struct size = 44 bytes exactly
- Ensure `long long timestamp` (not `long`)

### No Signals Generated
- Strategy is selective - HOLD signals are normal
- Verify you're testing during London/NY sessions
- Try different symbols or timeframes
- Check logs for detailed rejection reasons
- "No rejection pattern" means no valid S/R bounce found

### Import Errors
- Run `pip install -r requirements.txt`
- Ensure you're using Python 3.8+

## License

MIT License - Free to use and modify

## Support

### Testing Individual Modules

Each module has standalone tests:

```bash
python data.py          # Test MT5 connection
python sr_levels.py     # Test S/R detection
python rejection.py     # Test rejection patterns
python trade_setup.py   # Test trade setup
python logger.py        # Test logging system
python monitor.py       # Test performance monitoring
```

### Check Logs

Detailed logs are saved in `logs/volarix4_YYYY-MM-DD.log`

### Run Full Test Suite

```bash
python tests/test_api.py      # Complete API testing
python tests/backtest.py      # Development backtest
```
