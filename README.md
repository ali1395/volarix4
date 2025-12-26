# Volarix 4 - S/R Bounce Trading API

A minimal, production-ready REST API for generating trading signals based on Support/Resistance bounce patterns. Built with FastAPI and MetaTrader 5.

## Features

- **Pure S/R Strategy**: No machine learning, just proven price action
- **Volarix 3 Compatible**: Drop-in replacement with same API interface
- **4-Stage Pipeline**: Data → S/R Detection → Rejection Pattern → Signal
- **Session Filtered**: Only trades during London (3-11am EST) and NY (8am-4pm EST) sessions
- **Risk Management**: Automated SL/TP calculation with 1R/2R/3R targets

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
python start.py
```

The API will start on `http://localhost:8000`

## API Endpoints

### POST /signal

Generate trading signal for a symbol/timeframe.

**Request:**
```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "bars": 50
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
  -d '{"symbol":"EURUSD","timeframe":"H1","bars":50}'
```

### Using Python

```python
import requests

response = requests.post(
    "http://localhost:8000/signal",
    json={
        "symbol": "EURUSD",
        "timeframe": "H1",
        "bars": 50
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
├── main.py              # FastAPI application & endpoints
├── data.py              # MT5 data fetching
├── sr_levels.py         # S/R level detection
├── rejection.py         # Rejection pattern recognition
├── trade_setup.py       # SL/TP calculation
├── utils.py             # Helper functions
├── config.py            # Configuration
├── start.py             # Startup script
├── requirements.txt     # Dependencies
├── .env.example         # Environment template
└── README.md           # This file
```

## Requirements

- Python 3.8+
- MetaTrader 5 terminal (must be running)
- MT5 account with valid credentials

## Troubleshooting

### MT5 Connection Failed
- Ensure MT5 terminal is running
- Verify credentials in `.env` are correct
- Check that your MT5 account allows API access

### No Signals Generated
- Strategy is selective - HOLD signals are normal
- Verify you're testing during London/NY sessions
- Try different symbols or timeframes
- Check logs for detailed rejection reasons

### Import Errors
- Run `pip install -r requirements.txt`
- Ensure you're using Python 3.8+

## License

MIT License - Free to use and modify

## Support

For issues or questions, check the logs or test individual modules:

```bash
python data.py          # Test MT5 connection
python sr_levels.py     # Test S/R detection
python rejection.py     # Test rejection patterns
python trade_setup.py   # Test trade setup
```
