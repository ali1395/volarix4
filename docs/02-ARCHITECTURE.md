# Volarix 4 - Architecture Documentation

## System Architecture

Volarix 4 follows a **modular, pipeline-based architecture** where each component has a single, well-defined responsibility. The system processes market data through a series of stages to produce trading signals.

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT REQUEST                          │
│                   (HTTP POST /signal)                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FASTAPI APPLICATION                        │
│                        (main.py)                                │
│  - Request validation (Pydantic models)                         │
│  - Error handling & logging                                     │
│  - Performance monitoring                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SIGNAL GENERATION PIPELINE                  │
│                                                                 │
│  1. DATA FETCH       ┌──────────────────────────┐             │
│     (data.py)        │ MT5 Connection           │             │
│                      │ OHLCV Data Retrieval     │             │
│                      └───────────┬──────────────┘             │
│                                  │                             │
│  2. SESSION CHECK                ▼                             │
│     (data.py)        ┌──────────────────────────┐             │
│                      │ Validate Trading Hours   │             │
│                      │ London/NY Session Only   │             │
│                      └───────────┬──────────────┘             │
│                                  │                             │
│  3. S/R DETECTION                ▼                             │
│     (sr_levels.py)   ┌──────────────────────────┐             │
│                      │ Find Swing Highs/Lows    │             │
│                      │ Cluster Levels           │             │
│                      │ Score by Quality         │             │
│                      └───────────┬──────────────┘             │
│                                  │                             │
│  4. REJECTION SEARCH             ▼                             │
│     (rejection.py)   ┌──────────────────────────┐             │
│                      │ Find Pin Bars            │             │
│                      │ Validate Rejection       │             │
│                      │ Calculate Confidence     │             │
│                      └───────────┬──────────────┘             │
│                                  │                             │
│  5. TRADE SETUP                  ▼                             │
│     (trade_setup.py) ┌──────────────────────────┐             │
│                      │ Calculate Entry/SL/TP    │             │
│                      │ Apply Position Sizing    │             │
│                      │ Format Response          │             │
│                      └───────────┬──────────────┘             │
│                                  │                             │
└──────────────────────────────────┼─────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                         SIGNAL RESPONSE                         │
│          {signal, confidence, entry, sl, tp1-3, reason}         │
└─────────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. API Layer (`main.py`)

**Responsibility**: HTTP request/response handling, orchestration

**Key Functions**:
- FastAPI application setup and configuration
- Request validation using Pydantic models (`SignalRequest`, `SignalResponse`)
- Pipeline orchestration (calling each stage in sequence)
- Error handling and exception management
- Request/response logging
- Performance metric recording

**Technologies**:
- FastAPI for REST API framework
- Pydantic for data validation
- Uvicorn for ASGI web server

### 2. Data Module (`data.py`)

**Responsibility**: Market data acquisition and session validation

**Key Functions**:
- `connect_mt5()`: Establishes connection to MetaTrader 5 terminal
- `fetch_ohlc()`: Retrieves OHLCV (Open/High/Low/Close/Volume) bars
- `is_valid_session()`: Validates if current time is within trading sessions

**MT5 Integration**:
```python
# Connection flow
connect_mt5()
  → mt5.initialize()
  → mt5.login(login, password, server)
  → return connection status

# Data fetch flow
fetch_ohlc(symbol, timeframe, bars)
  → mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
  → Convert to pandas DataFrame
  → Return formatted OHLCV data
```

**Session Filter**:
- London session: 3:00 AM - 11:00 AM EST
- NY session: 8:00 AM - 4:00 PM EST
- Overlap: 8:00 AM - 11:00 AM EST (highest liquidity)

### 3. S/R Detection Module (`sr_levels.py`)

**Responsibility**: Identify and score Support/Resistance levels

**Algorithm Flow**:
```
1. Find Swing Points
   ├─ find_swing_highs() - Identify local maxima (resistance candidates)
   └─ find_swing_lows() - Identify local minima (support candidates)

2. Cluster Similar Levels
   └─ cluster_levels() - Group levels within 10 pips

3. Score Each Level (0-100)
   ├─ Base: 20 points per touch
   ├─ Recent touch bonus: +50 points
   └─ Strong rejection bonus: +20 points

4. Filter by Minimum Score
   └─ Keep only levels with score >= 60
```

**Swing Detection**:
- Window size: 5 bars (configurable)
- A swing high exists when high[i] > max(high[i-5:i]) AND high[i] > max(high[i+1:i+6])
- A swing low exists when low[i] < min(low[i-5:i]) AND low[i] < min(low[i+1:i+6])

**Level Scoring**:
```python
score = (touches × 20) + recent_touch_bonus + rejection_bonus
max_score = 100
```

### 4. Rejection Module (`rejection.py`)

**Responsibility**: Detect rejection candles (pin bars) at S/R levels

**Rejection Criteria**:

**For Support Rejection (BUY Signal)**:
- Low must touch support level (within 10 pips)
- Lower wick/body ratio > 1.5 (strong rejection wick)
- Lower wick must be dominant (longer than upper wick)
- Close must be in top 60% of candle range

**For Resistance Rejection (SELL Signal)**:
- High must touch resistance level (within 10 pips)
- Upper wick/body ratio > 1.5 (strong rejection wick)
- Upper wick must be dominant (longer than lower wick)
- Close must be in bottom 40% of candle range

**Confidence Calculation**:
```python
confidence = ((level_score / 100) + (wick_body_ratio / 10)) / 2
confidence = min(confidence, 1.0)  # Cap at 100%
```

### 5. Trade Setup Module (`trade_setup.py`)

**Responsibility**: Calculate entry, stop-loss, and take-profit levels

**Risk Management Rules**:
```
Stop-Loss (SL):
  - BUY: 10 pips below support level
  - SELL: 10 pips above resistance level

Take-Profit Levels:
  - TP1: 1R (Risk × 1) - Close 40% of position
  - TP2: 2R (Risk × 2) - Close 40% of position
  - TP3: 3R (Risk × 3) - Close 20% of position

Entry:
  - Close price of rejection candle
```

**Example Calculation (BUY)**:
```
Support Level: 1.08500
Entry (close): 1.08520
SL: 1.08500 - (10 pips × 0.0001) = 1.08490
Risk: 1.08520 - 1.08490 = 0.00030 (3 pips)

TP1: 1.08520 + (3 pips × 1R) = 1.08550
TP2: 1.08520 + (3 pips × 2R) = 1.08580
TP3: 1.08520 + (3 pips × 3R) = 1.08610
```

### 6. Configuration Module (`config.py`)

**Responsibility**: Centralized configuration management

**Configuration Categories**:

1. **S/R Detection Config** (`SR_CONFIG`)
   - Lookback period, swing window, min touches
   - Clustering threshold, minimum score

2. **Rejection Criteria Config** (`REJECTION_CONFIG`)
   - Wick/body ratio threshold
   - Max distance from level
   - Close position requirements

3. **Risk Management Config** (`RISK_CONFIG`)
   - SL distance, TP ratios, position sizing
   - Minimum risk:reward ratio

4. **Session Config** (`SESSIONS`)
   - London/NY session hours in EST

5. **API Config**
   - Host, port, debug mode

### 7. Utilities Module (`utils.py`)

**Responsibility**: Helper functions and utilities

**Functions**:
- `calculate_pip_value()`: Get pip size for symbol (0.0001 for majors, 0.01 for JPY pairs)
- `pips_to_price()`: Convert pips to price difference
- `price_to_pips()`: Convert price difference to pips
- `format_price()`: Format prices with correct decimal places
- `get_current_est_hour()`: Get current EST hour for session validation

### 8. Logging Module (`logger.py`)

**Responsibility**: Structured logging system

**Features**:
- Daily log rotation (logs/volarix4_YYYY-MM-DD.log)
- Colored console output for different log levels
- Structured log format with timestamps
- Detailed signal logging with `log_signal_details()`

**Log Levels**:
- DEBUG: Detailed debugging information
- INFO: General informational messages
- WARNING: Warning messages (e.g., multi-TF fallback)
- ERROR: Error messages with stack traces

### 9. Monitoring Module (`monitor.py`)

**Responsibility**: Real-time performance tracking

**Metrics Tracked**:
- Total requests and success rate
- Response time statistics (avg/min/max)
- Signal distribution (BUY/SELL/HOLD counts)
- Average confidence by signal type
- Top requested symbols
- Requests per minute
- API uptime

**Usage**:
```python
from monitor import monitor

# Record request
monitor.record_request(
    duration=0.125,
    signal="BUY",
    success=True,
    symbol="EURUSD",
    confidence=0.75
)

# Print statistics
monitor.print_stats()
```

## Data Flow

### Request Processing Flow

```
1. HTTP Request arrives
   └─ POST /signal with OHLCV data

2. Request Validation
   ├─ Validate JSON structure (Pydantic)
   ├─ Check required fields (symbol, timeframe, data)
   └─ Parse OHLCV bars

3. Data Processing
   └─ Convert bars to pandas DataFrame

4. Session Validation
   ├─ Check timestamp of latest bar
   └─ If outside session → Return HOLD

5. S/R Detection
   ├─ Find swing highs/lows
   ├─ Cluster levels
   ├─ Score levels
   └─ If no levels → Return HOLD

6. Rejection Search
   ├─ Check recent candles (last 5)
   ├─ Test against each S/R level
   ├─ Validate rejection criteria
   └─ If no rejection → Return HOLD

7. Trade Setup
   ├─ Calculate SL/TP levels
   ├─ Apply position sizing
   └─ Format response

8. Response
   └─ Return signal (BUY/SELL/HOLD) with risk parameters
```

## File Structure

```
volarix4/
├── main.py              # FastAPI app & orchestration
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
├── README.md            # Quick start guide
├── docs/                # Documentation (this folder)
│   ├── 01-PROJECT-OVERVIEW.md
│   ├── 02-ARCHITECTURE.md
│   ├── 03-STRATEGY-LOGIC.md
│   ├── 04-API-REFERENCE.md
│   └── 05-DEVELOPMENT-GUIDE.md
├── mt5_integration/     # MT5 Expert Advisor integration
│   ├── volarix4.mq5     # MQL5 Expert Advisor
│   ├── volarix.cpp      # C++ helper library
│   └── README_MT5.md    # MT5 integration guide
└── logs/                # Application logs
    └── volarix4_YYYY-MM-DD.log
```

## Design Principles

### 1. Modularity
Each module has a single, well-defined responsibility and can be tested independently.

### 2. Pipeline Architecture
Data flows through a linear pipeline where each stage transforms or filters the data.

### 3. Fail-Fast
If any stage cannot produce a valid result, return HOLD signal immediately.

### 4. Configuration-Driven
All strategy parameters are centralized in `config.py` for easy tuning.

### 5. Type Safety
Pydantic models ensure type safety and automatic validation.

### 6. Observability
Comprehensive logging and monitoring at every stage.

### 7. Backward Compatibility
API matches Volarix 3 interface for drop-in replacement.

## Deployment Architecture

### Single Server Deployment
```
┌─────────────────────────────────────────┐
│         Production Server               │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │  Uvicorn (ASGI Server)           │ │
│  │  Port: 8000                       │ │
│  │  Workers: 1 (MT5 connection)     │ │
│  └───────────────────────────────────┘ │
│                │                        │
│                ▼                        │
│  ┌───────────────────────────────────┐ │
│  │  FastAPI Application             │ │
│  │  (Volarix 4 Signal Engine)       │ │
│  └───────────────────────────────────┘ │
│                │                        │
│                ▼                        │
│  ┌───────────────────────────────────┐ │
│  │  MetaTrader 5 Terminal           │ │
│  │  (Market Data Provider)          │ │
│  └───────────────────────────────────┘ │
│                                         │
└─────────────────────────────────────────┘
```

### Integration with Trading Bots
```
┌──────────────┐      HTTP       ┌──────────────┐
│ Trading Bot  │ ────────────▶   │ Volarix 4    │
│  (Client)    │                 │  API Server  │
│              │ ◀────────────   │              │
└──────────────┘   JSON Signal   └──────────────┘

┌──────────────┐      DLL        ┌──────────────┐
│ MT5 EA       │ ────────────▶   │ Volarix 4    │
│ (MQL5)       │                 │  API Server  │
│              │ ◀────────────   │              │
└──────────────┘   HTTP Request  └──────────────┘
```

## Scalability Considerations

### Current Limitations
- **Single MT5 Connection**: Can only maintain one MT5 connection per instance
- **Synchronous Processing**: Each request is processed sequentially
- **Stateless**: No trade state management (external systems handle this)

### Future Scaling Options
1. **Horizontal Scaling**: Multiple instances behind load balancer (each with own MT5 connection)
2. **Caching**: Cache S/R levels for frequently requested symbols
3. **WebSocket Support**: Real-time signal streaming instead of polling
4. **Database Integration**: Store historical signals and performance data
