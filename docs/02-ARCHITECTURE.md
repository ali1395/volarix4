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
│                          (10-Stage Filter)                      │
│                                                                 │
│  1. BAR VALIDATION          ┌──────────────────────────┐       │
│     (bar_validation.py)     │ Normalize & Validate     │       │
│                             │ Check Timestamps         │       │
│                             │ Verify Closed Bars       │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│  2. SESSION FILTER          ▼                                   │
│     (data.py)               ┌──────────────────────────┐       │
│                             │ Validate Trading Hours   │       │
│                             │ London/NY Session Only   │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│  3. TREND FILTER            ▼                                   │
│     (trend_filter.py)       ┌──────────────────────────┐       │
│                             │ Calculate EMA 20/50      │       │
│                             │ Detect Trend Direction   │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│  4. S/R DETECTION           ▼                                   │
│     (sr_levels.py)          ┌──────────────────────────┐       │
│                             │ Find Swing Highs/Lows    │       │
│                             │ Cluster Levels           │       │
│                             │ Score by Quality         │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│  5. BROKEN LEVEL FILTER     ▼                                   │
│     (sr_validation.py)      ┌──────────────────────────┐       │
│                             │ Track Broken Levels      │       │
│                             │ Apply 48h Cooldown       │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│  6. REJECTION SEARCH        ▼                                   │
│     (rejection.py)          ┌──────────────────────────┐       │
│                             │ Find Pin Bars            │       │
│                             │ Validate Rejection       │       │
│                             │ Calculate Confidence     │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│  7. CONFIDENCE FILTER       ▼                                   │
│     (main.py)               ┌──────────────────────────┐       │
│                             │ Check >= 0.60 Threshold  │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│  8. TREND ALIGNMENT         ▼                                   │
│     (trend_filter.py)       ┌──────────────────────────┐       │
│                             │ Validate Signal vs Trend │       │
│                             │ Bypass if Conf >= 0.75   │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│  9. SIGNAL COOLDOWN         ▼                                   │
│     (main.py)               ┌──────────────────────────┐       │
│                             │ Check 2h per Symbol      │       │
│                             │ Prevent Over-Trading     │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│ 10. MIN EDGE FILTER         ▼                                   │
│     (trade_setup.py)        ┌──────────────────────────┐       │
│                             │ Validate TP > Costs + 4  │       │
│                             │ Ensure Profitable Edge   │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
└─────────────────────────────────────────┼───────────────────────┘
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

### 6. Bar Validation Module (`bar_validation.py`)

**Responsibility**: Validate and normalize OHLCV bar data

**Key Functions**:
- Verify strictly increasing timestamps (oldest → newest)
- Validate decision bar is closed (not forming)
- Check minimum 200 bars required
- Normalize bar data structure

**Validation Flow**:
```python
validate_bars(bars)
  → Check timestamps are strictly increasing
  → Verify last bar is closed (time_since_last_bar >= timeframe_seconds)
  → Validate minimum lookback (400 bars per Parity Contract)
  → Return normalized DataFrame
```

**Critical for Parity**: Ensures backtest and API use identical bar data (closed bars only, no forming bars).

### 7. Trend Filter Module (`trend_filter.py`)

**Responsibility**: Detect market trend using EMA crossover

**Algorithm**:
```python
# Calculate EMAs
ema_fast = df['close'].ewm(span=20).mean()  # 20-period EMA
ema_slow = df['close'].ewm(span=50).mean()  # 50-period EMA

# Detect trend
if ema_fast > ema_slow:
    trend = "UPTREND"   # Allow BUY, reject SELL (unless high confidence)
elif ema_fast < ema_slow:
    trend = "DOWNTREND" # Allow SELL, reject BUY (unless high confidence)
else:
    trend = "RANGING"   # Allow both
```

**High Confidence Bypass**:
- If confidence >= 0.75, allow counter-trend trades
- Rationale: Very strong rejection patterns may overcome trend

### 8. Broken Level Filter (`sr_validation.py`)

**Responsibility**: Track S/R levels that have been broken and apply cooldown

**Why It Matters**:
- Once support becomes resistance (or vice versa), reliability decreases
- Need time for new level psychology to form
- Prevents false signals at recently broken levels

**Broken Level Criteria**:
```python
# Support Broken
if price_low < support - (15 pips × pip_value):
    mark_broken(support, timestamp)
    apply_cooldown(48 hours)

# Resistance Broken
if price_high > resistance + (15 pips × pip_value):
    mark_broken(resistance, timestamp)
    apply_cooldown(48 hours)
```

**Cooldown Period**: 48 hours (configurable)

### 9. Confidence & Edge Filters (`main.py`, `trade_setup.py`)

**Confidence Filter** (main.py):
- Minimum threshold: 0.60 (default, configurable via API)
- Rejects signals below confidence threshold
- Balances quality vs quantity (0.60 optimized via backtest)

**Signal Cooldown** (main.py):
- Enforces 2-hour delay between signals per symbol
- Prevents over-trading and revenge trading
- Tracks last signal time per symbol in-memory

**Min Edge Filter** (trade_setup.py):
- Ensures TP1 distance > total_cost_pips + min_edge_pips
- Default min_edge: 4.0 pips after costs
- Cost model includes spread, slippage, and commission

**Cost Calculation**:
```python
# Round-trip costs
commission_pips = (2 × commission_per_side × lot_size) / usd_per_pip_per_lot
total_cost_pips = spread_pips + (2 × slippage_pips) + commission_pips

# Edge requirement
if TP1_distance_pips <= total_cost_pips + min_edge_pips:
    return HOLD  # Insufficient profitable edge
```

### 10. Configuration Module (`config.py`)

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

### Request Processing Flow (10-Stage Pipeline)

```
1. HTTP Request arrives
   └─ POST /signal with OHLCV data

2. Request Validation
   ├─ Validate JSON structure (Pydantic)
   ├─ Check required fields (symbol, timeframe, data)
   └─ Parse OHLCV bars

3. Bar Validation
   ├─ Verify strictly increasing timestamps
   ├─ Check last bar is closed (not forming)
   └─ If invalid → Return 422 ERROR

4. Session Filter
   ├─ Check timestamp of decision bar
   └─ If outside London/NY → Return HOLD

5. Trend Filter
   ├─ Calculate EMA 20/50
   ├─ Detect trend direction
   └─ Store for trend alignment check (stage 9)

6. S/R Detection
   ├─ Find swing highs/lows
   ├─ Cluster levels
   ├─ Score levels (min score 60)
   └─ If no levels → Return HOLD

7. Broken Level Filter
   ├─ Check broken level cooldown (48h)
   ├─ Remove levels in cooldown period
   └─ If all broken → Return HOLD

8. Rejection Search
   ├─ Check recent candles (last 5)
   ├─ Test against valid S/R levels
   ├─ Validate rejection criteria
   ├─ Calculate confidence score
   └─ If no rejection → Return HOLD

9. Confidence Filter
   ├─ Check confidence >= min_confidence (0.60)
   └─ If too low → Return HOLD

10. Trend Alignment
    ├─ Validate signal aligns with trend
    ├─ BYPASS if confidence >= 0.75
    └─ If misaligned → Return HOLD

11. Signal Cooldown
    ├─ Check last signal time for symbol
    ├─ Enforce 2-hour minimum delay
    └─ If in cooldown → Return HOLD

12. Min Edge Filter
    ├─ Calculate total costs (spread + slippage + commission)
    ├─ Check TP1 distance > costs + min_edge_pips (4.0)
    └─ If insufficient edge → Return HOLD

13. Trade Setup
    ├─ Calculate SL/TP levels
    ├─ Apply position sizing
    └─ Format response

14. Response
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
