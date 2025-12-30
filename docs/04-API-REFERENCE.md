# Volarix 4 - API Reference

## Base URL

```
http://localhost:8000
```

Change host and port in `.env` file or `config.py`.

## Authentication

Currently no authentication required. For production deployment, consider adding:
- API key authentication
- JWT tokens
- IP whitelisting
- Rate limiting

## Endpoints

### 1. GET `/`

Root endpoint with API information.

#### Request

```bash
curl http://localhost:8000/
```

#### Response

```json
{
  "name": "Volarix 4",
  "version": "4.0.0",
  "status": "online",
  "description": "S/R Bounce Trading API",
  "endpoints": {
    "/signal": "POST - Generate trading signal",
    "/health": "GET - Health check",
    "/docs": "GET - API documentation"
  }
}
```

---

### 2. GET `/health`

Health check endpoint for monitoring service status.

#### Request

```bash
curl http://localhost:8000/health
```

#### Response

**Success (200 OK)**:
```json
{
  "status": "healthy",
  "mt5_connected": true,
  "version": "4.0.0"
}
```

**MT5 Disconnected**:
```json
{
  "status": "healthy",
  "mt5_connected": false,
  "version": "4.0.0"
}
```

#### Use Case

- Monitoring and alerting (check if service is running)
- Load balancer health checks
- Verify MT5 connection status before sending signal requests

---

### 3. POST `/signal`

Generate trading signal from OHLCV data.

#### Request

**Headers**:
```
Content-Type: application/json
```

**Body Schema**:
```json
{
  "symbol": "string",                    // Required: Trading pair (e.g., "EURUSD")
  "timeframe": "string",                 // Required: Timeframe (e.g., "H1", "M15")
  "data": [                              // Required: Array of OHLCV bars
    {
      "time": 1640000000,                // Unix timestamp (seconds)
      "open": 1.08500,                   // Open price
      "high": 1.08600,                   // High price
      "low": 1.08400,                    // Low price
      "close": 1.08550,                  // Close price
      "volume": 1000                     // Volume (integer)
    }
  ],

  // Optional: Legacy V3 compatibility (ignored in V4)
  "execution_timeframe": "string",       // Explicit execution TF (defaults to timeframe)
  "context_timeframe": "string",         // Context TF (ignored in V4)
  "context_data": [],                    // Context bars (ignored in V4)
  "model_type": "string",                // Model type (ignored in V4)

  // Optional: Strategy parameters (override defaults)
  "min_confidence": 0.60,                // Minimum confidence threshold (0.0-1.0)
  "broken_level_cooldown_hours": 48.0,   // Hours to wait after level break
  "broken_level_break_pips": 15.0,       // Pips beyond level = broken
  "min_edge_pips": 4.0,                  // Min profitable edge after costs

  // Optional: Cost model parameters (override defaults)
  "spread_pips": 1.0,                    // Broker spread in pips
  "slippage_pips": 0.5,                  // Expected slippage per side
  "commission_per_side_per_lot": 7.0,    // USD commission per lot per side
  "usd_per_pip_per_lot": 10.0,           // Standard lot pip value
  "lot_size": 1.0                        // Lot size for commission calc
}
```

**Field Descriptions**:

**Required Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | string | Trading pair symbol (e.g., "EURUSD", "GBPUSD") |
| `timeframe` | string | Chart timeframe (M1, M5, M15, M30, H1, H4, D1, W1) |
| `data` | array | OHLCV bars (minimum 400 recommended for S/R detection) |

**Optional Fields (Legacy V3 Compatibility):**

| Field | Type | Description |
|-------|------|-------------|
| `execution_timeframe` | string | Override timeframe (defaults to `timeframe`) |
| `context_timeframe` | string | Multi-TF context (Volarix 3 compatibility, ignored) |
| `context_data` | array | Context TF bars (Volarix 3 compatibility, ignored) |
| `model_type` | string | Model type (Volarix 3 compatibility, ignored) |

**Optional Fields (Strategy Parameters):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `min_confidence` | float | 0.60 | Minimum confidence score to accept signal (0.0-1.0) |
| `broken_level_cooldown_hours` | float | 48.0 | Hours to exclude broken S/R levels from consideration |
| `broken_level_break_pips` | float | 15.0 | Pips beyond level to consider it "broken" |
| `min_edge_pips` | float | 4.0 | Minimum profitable pips after all costs |

**Optional Fields (Cost Model Parameters):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `spread_pips` | float | 1.0 | Bid/ask spread in pips |
| `slippage_pips` | float | 0.5 | Expected slippage per order (one-way) |
| `commission_per_side_per_lot` | float | 7.0 | Commission in USD per lot per side |
| `usd_per_pip_per_lot` | float | 10.0 | Dollar value per pip for 1 standard lot |
| `lot_size` | float | 1.0 | Lot size for commission calculation |

**OHLCV Bar Schema**:

| Field | Type | Description |
|-------|------|-------------|
| `time` | integer | Unix timestamp in seconds |
| `open` | float | Open price |
| `high` | float | High price |
| `low` | float | Low price |
| `close` | float | Close price |
| `volume` | integer | Volume (tick volume) |

#### Example Request

**Using cURL**:
```bash
curl -X POST http://localhost:8000/signal \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "timeframe": "H1",
    "data": [
      {
        "time": 1640000000,
        "open": 1.08500,
        "high": 1.08600,
        "low": 1.08400,
        "close": 1.08550,
        "volume": 1000
      },
      {
        "time": 1640003600,
        "open": 1.08550,
        "high": 1.08650,
        "low": 1.08500,
        "close": 1.08600,
        "volume": 1200
      }
    ]
  }'
```

**Using Python**:
```python
import requests

response = requests.post(
    "http://localhost:8000/signal",
    json={
        "symbol": "EURUSD",
        "timeframe": "H1",
        "data": [
            {
                "time": 1640000000,
                "open": 1.08500,
                "high": 1.08600,
                "low": 1.08400,
                "close": 1.08550,
                "volume": 1000
            },
            # ... more bars
        ]
    }
)

signal = response.json()
print(f"Signal: {signal['signal']}")
print(f"Entry: {signal['entry']}")
print(f"SL: {signal['sl']}")
print(f"TP1: {signal['tp1']}")
```

**Using JavaScript**:
```javascript
const response = await fetch('http://localhost:8000/signal', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    symbol: 'EURUSD',
    timeframe: 'H1',
    data: [
      {
        time: 1640000000,
        open: 1.08500,
        high: 1.08600,
        low: 1.08400,
        close: 1.08550,
        volume: 1000
      }
      // ... more bars
    ]
  })
});

const signal = await response.json();
console.log(`Signal: ${signal.signal}`);
```

#### Response

**Success (200 OK)**:

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

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `signal` | string | Trade signal: "BUY", "SELL", or "HOLD" |
| `confidence` | float | Confidence score (0.0 - 1.0) |
| `entry` | float | Entry price |
| `sl` | float | Stop-loss price |
| `tp1` | float | First take-profit price (1R) |
| `tp2` | float | Second take-profit price (2R) |
| `tp3` | float | Third take-profit price (3R) |
| `tp1_percent` | float | Position % to close at TP1 (0.4 = 40%) |
| `tp2_percent` | float | Position % to close at TP2 (0.4 = 40%) |
| `tp3_percent` | float | Position % to close at TP3 (0.2 = 20%) |
| `reason` | string | Human-readable explanation of signal |

#### Signal Types

**BUY Signal**:
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
- **Meaning**: Price rejected from support, enter long
- **Entry**: Close of rejection candle
- **SL**: Below support level
- **TP**: Above entry at 1R, 2R, 3R multiples

**SELL Signal**:
```json
{
  "signal": "SELL",
  "confidence": 0.68,
  "entry": 1.08980,
  "sl": 1.09110,
  "tp1": 1.08850,
  "tp2": 1.08720,
  "tp3": 1.08590,
  "tp1_percent": 0.4,
  "tp2_percent": 0.4,
  "tp3_percent": 0.2,
  "reason": "Resistance bounce at 1.09000, score 70.0"
}
```
- **Meaning**: Price rejected from resistance, enter short
- **Entry**: Close of rejection candle
- **SL**: Above resistance level
- **TP**: Below entry at 1R, 2R, 3R multiples

**HOLD Signal** (No Setup Found):
```json
{
  "signal": "HOLD",
  "confidence": 0.0,
  "entry": 0.0,
  "sl": 0.0,
  "tp1": 0.0,
  "tp2": 0.0,
  "tp3": 0.0,
  "tp1_percent": 0.4,
  "tp2_percent": 0.4,
  "tp3_percent": 0.2,
  "reason": "No rejection pattern at S/R levels"
}
```
- **Meaning**: No valid trading setup, stay out
- **Common HOLD Rejection Reasons** (10-Stage Pipeline):
  1. `"Invalid bars (timestamps not increasing)"`
  2. `"Outside trading session (London/NY only)"`
  3. `"No significant S/R levels detected (score >= 60)"`
  4. `"All S/R levels broken or in cooldown period (48h)"`
  5. `"No rejection pattern at valid S/R levels"`
  6. `"Confidence below threshold (X.XX < 0.60)"`
  7. `"Trend alignment failed: [signal] in [trend]"` (bypassed if confidence >= 0.75)
  8. `"Signal cooldown active: next signal allowed after HH:MM:SS"`
  9. `"Insufficient edge after costs (TP1 X.X pips <= costs Y.Y + edge Z.Z)"`
  10. General errors during processing

#### Error Responses

**Validation Error (422 Unprocessable Entity)**:
```json
{
  "detail": [
    {
      "loc": ["body", "symbol"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ],
  "body": "{...}",
  "expected_format": {
    "symbol": "string (e.g., EURUSD)",
    "timeframe": "string (e.g., H1, M15, D1)",
    "data": "array of OHLCV bars [{time, open, high, low, close, volume}]"
  }
}
```

**Internal Server Error (500)**:
```json
{
  "detail": "Internal server error"
}
```

#### Best Practices

1. **Minimum Data**: Send at least 400 bars for reliable S/R detection and EMA trend filter
2. **Data Quality**: Ensure OHLCV data is accurate and complete
3. **Timestamps**: Use Unix timestamps in seconds (not milliseconds)
4. **Timeframes**: Use standard MT5 timeframe strings (M1, M5, M15, M30, H1, H4, D1, W1)
5. **Symbol Format**: Use standard broker symbol names (e.g., "EURUSD", not "EUR/USD")
6. **Handle HOLD**: HOLD signals are normal and expected (quality over quantity)

#### Backtest Parity Mode

For ensuring backtest-live parity, use these exact parameters (matches `BACKTEST_PARITY_CONFIG`):

```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "data": [...],  // 400+ closed bars only

  // Backtest parity parameters
  "min_confidence": 0.60,
  "broken_level_cooldown_hours": 48.0,
  "broken_level_break_pips": 15.0,
  "min_edge_pips": 4.0,
  "spread_pips": 1.0,
  "slippage_pips": 0.5,
  "commission_per_side_per_lot": 7.0,
  "usd_per_pip_per_lot": 10.0,
  "lot_size": 1.0
}
```

**Critical for Parity:**
- Send **closed bars only** (no forming bar at index 0)
- Send exactly 400 bars (or more, but consistent with backtest)
- Use identical cost parameters as backtest
- Ensure bar timestamps are strictly increasing (oldest → newest)
- Last bar should be the decision bar (closed, not forming)

**MT5 EA Parity Mode:**
The MT5 EA (`volarix4.mq5`) has a `BacktestParityMode` option that automatically sends these parameters. When enabled, the EA overrides manual inputs and forces backtest-matching values.

**See**: `docs/PARITY_CONTRACT.md` and `docs/BACKTEST_PARITY.md` for comprehensive parity documentation.

---

### 4. GET `/docs`

Interactive API documentation (Swagger UI).

#### Request

```bash
# Open in browser
http://localhost:8000/docs
```

#### Features

- Interactive API testing
- Request/response schemas
- Try out endpoints directly
- Auto-generated from FastAPI

---

### 5. GET `/redoc`

Alternative API documentation (ReDoc).

#### Request

```bash
# Open in browser
http://localhost:8000/redoc
```

#### Features

- Clean, readable documentation
- Better for printing/exporting
- No interactive testing

---

## Integration Examples

### Python Trading Bot

```python
import requests
import time

API_URL = "http://localhost:8000/signal"

def get_signal(symbol, timeframe, bars):
    """Fetch trading signal from Volarix 4 API."""
    response = requests.post(
        API_URL,
        json={
            "symbol": symbol,
            "timeframe": timeframe,
            "data": bars  # Your OHLCV data
        },
        timeout=10
    )
    response.raise_for_status()
    return response.json()

def execute_trade(signal):
    """Execute trade based on signal."""
    if signal['signal'] == 'HOLD':
        print("No trade - HOLD signal")
        return

    print(f"Signal: {signal['signal']}")
    print(f"Entry: {signal['entry']}")
    print(f"SL: {signal['sl']}")
    print(f"TP1: {signal['tp1']}")
    print(f"TP2: {signal['tp2']}")
    print(f"TP3: {signal['tp3']}")
    print(f"Reason: {signal['reason']}")

    # TODO: Place order with your broker

# Main loop
while True:
    bars = fetch_market_data("EURUSD", "H1", 400)  # Your data source
    signal = get_signal("EURUSD", "H1", bars)
    execute_trade(signal)
    time.sleep(3600)  # Check every hour
```

### MT5 Expert Advisor (MQL5)

See `mt5_integration/volarix4.mq5` for complete implementation:

```mql5
// Simplified example
string url = "http://localhost:8000/signal";
string headers = "Content-Type: application/json\r\n";

// Build JSON request
string json = BuildSignalRequest("EURUSD", "H1", 50);

// Send HTTP request
char post[], result[];
StringToCharArray(json, post);
int res = WebRequest("POST", url, headers, 5000, post, result, headers);

// Parse response
string response = CharArrayToString(result);
string signal = ParseSignal(response);

if (signal == "BUY") {
    // Place buy order
    double entry = ParseEntry(response);
    double sl = ParseSL(response);
    double tp = ParseTP(response);
    trade.Buy(lots, Symbol(), entry, sl, tp);
}
```

### Node.js Integration

```javascript
const axios = require('axios');

async function getSignal(symbol, timeframe, bars) {
  try {
    const response = await axios.post('http://localhost:8000/signal', {
      symbol: symbol,
      timeframe: timeframe,
      data: bars
    });

    const signal = response.data;
    console.log(`Signal: ${signal.signal}`);
    console.log(`Confidence: ${signal.confidence}`);
    console.log(`Reason: ${signal.reason}`);

    if (signal.signal !== 'HOLD') {
      console.log(`Entry: ${signal.entry}`);
      console.log(`SL: ${signal.sl}`);
      console.log(`TP1: ${signal.tp1} (${signal.tp1_percent * 100}%)`);
      console.log(`TP2: ${signal.tp2} (${signal.tp2_percent * 100}%)`);
      console.log(`TP3: ${signal.tp3} (${signal.tp3_percent * 100}%)`);
    }

    return signal;
  } catch (error) {
    console.error('Error fetching signal:', error.message);
    throw error;
  }
}

// Usage
const bars = fetchMarketData('EURUSD', 'H1', 400);
getSignal('EURUSD', 'H1', bars);
```

## Rate Limiting

Currently no rate limiting is enforced. For production deployment, consider:

- Limit requests per IP address (e.g., 60 requests/minute)
- Implement API key quotas
- Add caching for repeated requests with same data

## Error Handling

### Client-Side Error Handling

```python
import requests
from requests.exceptions import Timeout, ConnectionError

try:
    response = requests.post(
        "http://localhost:8000/signal",
        json={"symbol": "EURUSD", "timeframe": "H1", "data": bars},
        timeout=10
    )
    response.raise_for_status()
    signal = response.json()

except Timeout:
    print("Request timed out - API may be overloaded")

except ConnectionError:
    print("Could not connect to API - is it running?")

except requests.exceptions.HTTPError as e:
    if e.response.status_code == 422:
        print("Invalid request format:", e.response.json())
    elif e.response.status_code == 500:
        print("Server error:", e.response.json())

except Exception as e:
    print(f"Unexpected error: {e}")
```

## Performance

### Typical Response Times

- **Health check**: < 10 ms
- **Signal generation**: 50-200 ms (depends on data size)
- **With MT5 fetch**: 200-500 ms (depends on MT5 connection)

### Optimization Tips

1. **Batch Processing**: If checking multiple symbols, use async requests
2. **Caching**: Cache S/R levels if analyzing same symbol repeatedly
3. **Data Size**: Send 400+ bars for optimal S/R detection and trend analysis
4. **Connection Pooling**: Reuse HTTP connections for multiple requests

## Monitoring

### Health Check Integration

```python
import requests

def check_api_health():
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        health = response.json()

        if health['status'] == 'healthy' and health['mt5_connected']:
            return True
        else:
            print(f"API unhealthy: {health}")
            return False
    except:
        print("API unreachable")
        return False

# Use in monitoring loop
if not check_api_health():
    send_alert("Volarix 4 API is down!")
```

### Logging

API logs all requests to `logs/volarix4_YYYY-MM-DD.log`:

```
2024-01-15 10:30:45 - INFO - >> POST /signal
2024-01-15 10:30:45 - INFO - Signal request: EURUSD [Single-TF] | Fields: tf=H1 ...
2024-01-15 10:30:45 - INFO - DATA_FETCH: {'bars_count': 400, 'start_date': ...}
2024-01-15 10:30:45 - INFO - SR_DETECTION: {'levels_count': 3, 'levels': [...]}
2024-01-15 10:30:45 - INFO - REJECTION_SEARCH: {'found': True, 'direction': 'BUY', ...}
2024-01-15 10:30:45 - INFO - FINAL_SIGNAL: {'signal': 'BUY', 'confidence': 0.75, ...}
2024-01-15 10:30:45 - INFO - << POST /signal - Status: 200
```

## Changelog

### Version 4.0.0
- Initial release
- S/R bounce strategy implementation
- Volarix 3 API compatibility
- MT5 integration
- Comprehensive logging and monitoring
