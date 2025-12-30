# Volarix 4 - Strategy & Logic Documentation

## Trading Strategy Overview

Volarix 4 implements a **Support/Resistance (S/R) Bounce Strategy** based on pure price action. The strategy identifies key support and resistance levels, waits for price to reject from these levels with strong confirmation (pin bars), and enters trades with predefined risk management.

## Strategy Philosophy

### Core Concepts

1. **Support & Resistance Are Not Lines, They Are Zones**
   - Levels are clustered within 10 pips to account for spread and noise
   - Price doesn't need to touch exact level, just come within proximity

2. **Rejection Strength Matters**
   - Not every touch is tradeable
   - Only trade strong rejections with clear wicks (wick/body ratio > 1.5)
   - Close must be favorable (away from the rejection zone)

3. **Quality Over Quantity**
   - Only trade during high-liquidity sessions (London/NY)
   - Only trade levels with high quality scores (multiple touches, recent activity)
   - Better to wait for perfect setups than force trades

4. **Risk Management First**
   - Always know your stop-loss before entering
   - Scale out at multiple targets (1R, 2R, 3R)
   - Maximum risk clearly defined (10 pips beyond level)

## Strategy Components

### 1. Support/Resistance Level Detection

#### Swing Point Identification

**Swing High (Resistance Candidate)**:
```
A swing high exists at index i when:
  high[i] > max(high[i-5 : i])      AND
  high[i] > max(high[i+1 : i+6])

Visual:
         *  ← Swing High
        / \
       /   \
      /     \
     /       \
```

**Swing Low (Support Candidate)**:
```
A swing low exists at index i when:
  low[i] < min(low[i-5 : i])       AND
  low[i] < min(low[i+1 : i+6])

Visual:
     \       /
      \     /
       \   /
        \ /
         *  ← Swing Low
```

**Configuration**:
- Window size: 5 bars (configurable in `SR_CONFIG['swing_window']`)
- Lookback period: 50 bars (configurable in `SR_CONFIG['lookback']`)

#### Level Clustering

After identifying swing points, nearby levels are clustered together:

```python
# Example: Multiple swing lows near 1.0850
swing_lows = [1.08495, 1.08502, 1.08485, 1.08510]

# After clustering within 10 pips
clustered_level = 1.08498  # Average of the cluster
```

**Why Cluster?**
- Price rarely bounces from the exact same price
- Accounts for spread, slippage, and minor variations
- Creates stronger, more reliable S/R zones

**Configuration**:
- Cluster threshold: 10 pips (configurable in `SR_CONFIG['cluster_pips']`)

#### Level Scoring

Each S/R level is scored from 0-100 based on:

| Criteria | Points | Description |
|----------|--------|-------------|
| **Touches** | 20 per touch | Number of times price touched this level |
| **Recency** | +50 | Level touched in last 20 bars |
| **Strong Rejection** | +20 | Large wick rejection at level (wick/body > 1.5) |

**Scoring Formula**:
```python
score = (touches × 20) + recency_bonus + rejection_bonus
score = min(score, 100)  # Cap at 100
```

**Examples**:
```
Level at 1.0850 with 3 touches, recent touch, no strong rejection:
  score = (3 × 20) + 50 + 0 = 110 → 100 (capped)

Level at 1.0900 with 2 touches, old, strong rejection:
  score = (2 × 20) + 0 + 20 = 60

Level at 1.0920 with 2 touches, not recent, no rejection:
  score = (2 × 20) + 0 + 0 = 40 → REJECTED (< 60 threshold)
```

**Minimum Score Threshold**: 60 (configurable in `SR_CONFIG['min_level_score']`)

### 2. Rejection Pattern Recognition

A rejection pattern is a candle that shows price was "rejected" from an S/R level, indicating strong buying (at support) or selling (at resistance) pressure.

#### Support Rejection (BUY Signal)

**Required Conditions**:

1. **Level Touch**: Low of candle within 10 pips of support level
   ```
   abs(candle_low - support_level) <= 10 pips
   ```

2. **Strong Lower Wick**: Wick must be significantly larger than body
   ```
   lower_wick / body > 1.5
   ```

3. **Dominant Lower Wick**: Lower wick must be longer than upper wick
   ```
   lower_wick > upper_wick
   ```

4. **Favorable Close**: Close must be in top 60% of candle range
   ```
   close_position = (close - low) / (high - low)
   close_position >= 0.60  (top 40% of candle)
   ```

**Visual Example**:
```
    ┌─┐ ← Close (top 60%)
    │ │
    │ │ Body
    │ │
    └─┘ ← Open
     │
     │  Lower Wick (> 1.5× body)
     │
     * ← Low touches support level
─────────── Support Level
```

#### Resistance Rejection (SELL Signal)

**Required Conditions**:

1. **Level Touch**: High of candle within 10 pips of resistance level
   ```
   abs(candle_high - resistance_level) <= 10 pips
   ```

2. **Strong Upper Wick**: Wick must be significantly larger than body
   ```
   upper_wick / body > 1.5
   ```

3. **Dominant Upper Wick**: Upper wick must be longer than lower wick
   ```
   upper_wick > lower_wick
   ```

4. **Favorable Close**: Close must be in bottom 40% of candle range
   ```
   close_position = (close - low) / (high - low)
   close_position <= 0.40  (bottom 40% of candle)
   ```

**Visual Example**:
```
─────────── Resistance Level
     * ← High touches resistance level
     │
     │  Upper Wick (> 1.5× body)
     │
    ┌─┐ ← Open
    │ │ Body
    │ │
    │ │
    └─┘ ← Close (bottom 40%)
```

#### Confidence Calculation

Each rejection is assigned a confidence score (0-1) based on:

```python
confidence = (
    (level_score / 100) +      # Level quality (0-1)
    (wick_body_ratio / 10)      # Rejection strength (0-1)
) / 2

confidence = min(confidence, 1.0)
```

**Examples**:
```
Strong rejection at high-quality level:
  level_score = 85, wick_body_ratio = 3.0
  confidence = ((85/100) + (3.0/10)) / 2 = 0.575

Weak rejection at medium-quality level:
  level_score = 65, wick_body_ratio = 1.6
  confidence = ((65/100) + (1.6/10)) / 2 = 0.405
```

### 3. Risk Management

#### Stop-Loss Placement

**Principle**: Stop-loss must be beyond the S/R level to avoid premature stops from minor whipsaws.

**BUY Signal**:
```
SL = support_level - (10 pips × pip_value)
```

**SELL Signal**:
```
SL = resistance_level + (10 pips × pip_value)
```

**Example (BUY)**:
```
Support level: 1.08500
Pip value: 0.0001
SL = 1.08500 - (10 × 0.0001) = 1.08490
```

#### Entry Price

**Entry = Close price of rejection candle**

This is a conservative approach:
- Avoids entering on the wick (less reliable)
- Confirms rejection has completed
- Slightly worse entry but higher probability

#### Take-Profit Levels

Three take-profit levels based on risk multiples (R):

| Target | Risk Multiple | Position % | Description |
|--------|---------------|------------|-------------|
| TP1 | 1R | 40% | Conservative first target |
| TP2 | 2R | 40% | Main profit target |
| TP3 | 3R | 20% | Runner target |

**Calculation**:
```python
risk = abs(entry - sl)

if BUY:
    tp1 = entry + (1.0 × risk)
    tp2 = entry + (2.0 × risk)
    tp3 = entry + (3.0 × risk)
else:  # SELL
    tp1 = entry - (1.0 × risk)
    tp2 = entry - (2.0 × risk)
    tp3 = entry - (3.0 × risk)
```

**Complete BUY Example**:
```
Support Level: 1.08500
Entry: 1.08520
SL: 1.08490
Risk: 1.08520 - 1.08490 = 0.00030 (3.0 pips)

TP1: 1.08520 + 0.00030 = 1.08550 (close 40%)
TP2: 1.08520 + 0.00060 = 1.08580 (close 40%)
TP3: 1.08520 + 0.00090 = 1.08610 (close 20%)
```

#### Position Sizing Strategy

**Scaling Out**:
```
Initial Position: 100%

At TP1 (1R): Close 40% → Remaining: 60%
At TP2 (2R): Close 40% → Remaining: 20%
At TP3 (3R): Close 20% → Remaining: 0%
```

**Expected Return**:
```
If all TPs hit:
  (40% × 1R) + (40% × 2R) + (20% × 3R) = 1.8R average per trade
```

**Why This Approach?**
- Locks in profits early (TP1)
- Captures strong moves (TP2)
- Lets winners run (TP3)
- Reduces emotional decision-making

### 4. Session Filtering

Only trade during high-liquidity sessions to ensure:
- Tighter spreads
- Better order execution
- More reliable price action
- Reduced slippage

**Trading Sessions (EST)**:

| Session | Hours (EST) | Reason |
|---------|-------------|--------|
| **London** | 3:00 AM - 11:00 AM | High EUR/GBP pairs volume |
| **New York** | 8:00 AM - 4:00 PM | High USD pairs volume |
| **Overlap** | 8:00 AM - 11:00 AM | Highest liquidity |

**Non-Trading Sessions**:
- Asian session (low volatility for EUR/USD, GBP/USD)
- After-hours (low liquidity, wider spreads)
- Weekends (market closed)

**Implementation**:
```python
def is_valid_session(timestamp):
    hour = timestamp.hour  # Assumes EST timezone

    # London: 3-11 EST
    in_london = 3 <= hour < 11

    # NY: 8-16 EST
    in_ny = 8 <= hour < 16

    return in_london or in_ny
```

### 5. Trend Filter (EMA 20/50)

Uses dual Exponential Moving Averages to identify market trend and filter trades accordingly.

**Trend Detection Logic**:
```python
ema_fast = df['close'].ewm(span=20).mean()  # 20-period EMA
ema_slow = df['close'].ewm(span=50).mean()  # 50-period EMA

if ema_fast > ema_slow:
    trend = "UPTREND"   # Bullish trend
elif ema_fast < ema_slow:
    trend = "DOWNTREND" # Bearish trend
else:
    trend = "RANGING"   # No clear trend
```

**Trend Alignment Rules**:
- **UPTREND**: Allow BUY signals, reject SELL signals
- **DOWNTREND**: Allow SELL signals, reject BUY signals
- **RANGING**: Allow both BUY and SELL signals

**High Confidence Bypass**:
- If confidence >= 0.75, allow counter-trend trades
- Example: SELL signal with 0.82 confidence allowed in UPTREND
- Rationale: Very strong rejection may overcome trend

**Configuration**:
```python
TREND_FILTER_CONFIG = {
    "ema_fast": 20,                      # Fast EMA period
    "ema_slow": 50,                      # Slow EMA period
    "min_confidence_for_bypass": 0.75    # Bypass threshold
}
```

### 6. Broken Level Filter

Tracks S/R levels that have been broken and applies cooldown period to prevent trading at unreliable levels.

**Why This Matters**:
- Once a support becomes resistance (or vice versa), it's less reliable
- Need time for new level psychology to form
- Prevents trading false signals at recently broken levels

**Broken Level Criteria**:

**Support Broken**:
```python
if price_low < support_level - (15 pips × pip_value):
    # Support is broken
    mark_broken(support_level, timestamp)
    apply_cooldown(48 hours)
```

**Resistance Broken**:
```python
if price_high > resistance_level + (15 pips × pip_value):
    # Resistance is broken
    mark_broken(resistance_level, timestamp)
    apply_cooldown(48 hours)
```

**Cooldown Period**: 48 hours (configurable)

**Implementation**:
- Tracks broken levels in-memory with timestamps
- Filters out levels still in cooldown before rejection search
- Logs broken level info for debugging

**Example**:
```
Support at 1.08500 broken at 2025-01-30 10:00 (price dropped to 1.08350)
→ Level unavailable until 2025-02-01 10:00 (48h later)
```

**Configuration**:
```python
BROKEN_LEVEL_CONFIG = {
    "cooldown_hours": 48.0,        # Hours to wait after break
    "break_threshold_pips": 15.0   # Pips beyond level = broken
}
```

### 7. Confidence Filter

Rejects signals below minimum confidence threshold to ensure trade quality.

**Confidence Calculation** (from rejection pattern):
```python
confidence = ((level_score / 100) + (wick_body_ratio / 10)) / 2
confidence = min(confidence, 1.0)  # Cap at 100%
```

**Minimum Threshold**: 0.60 (default, configurable via API)

**Why 0.60?**
- Backtesting shows optimal win rate at this threshold
- Too low (0.50): Many false signals, lower win rate
- Too high (0.70): Misses valid trades, lower opportunity
- 0.60 balances quality vs quantity

**Example Rejections**:
```
Signal: BUY, Confidence: 0.55
→ REJECTED: "Confidence below threshold (0.55 < 0.60)"

Signal: SELL, Confidence: 0.68
→ ACCEPTED: Confidence above threshold
```

### 8. Signal Cooldown

Prevents over-trading by enforcing time delay between signals for each symbol.

**Cooldown Period**: 2 hours (per symbol)

**Logic**:
```python
last_signal_time = get_last_signal_time(symbol)
current_time = datetime.now()
time_since_last_signal = current_time - last_signal_time

if time_since_last_signal < timedelta(hours=2):
    return HOLD  # In cooldown
```

**Benefits**:
- Reduces trading costs (commissions/spreads)
- Prevents revenge trading on similar setups
- Forces patience for better quality setups
- Reduces correlation between consecutive trades

**Example**:
```
EURUSD Signal 1: BUY at 10:00 → Trade opened
EURUSD Signal 2: BUY at 10:30 → REJECTED (cooldown)
EURUSD Signal 3: BUY at 11:30 → REJECTED (cooldown)
EURUSD Signal 4: BUY at 12:05 → ACCEPTED (>2h elapsed)

GBPUSD Signal 1: SELL at 10:15 → Trade opened (different symbol, independent cooldown)
```

**Configuration**:
```python
SIGNAL_COOLDOWN_CONFIG = {
    "cooldown_hours": 2.0  # Hours between signals per symbol
}
```

### 9. Minimum Edge Filter

Ensures sufficient profit potential after all costs to make the trade worthwhile.

**Cost Model**:
```python
# Round-trip costs
commission_pips = (2 × commission_per_side × lot_size) / usd_per_pip_per_lot
total_cost_pips = spread_pips + (2 × slippage_pips) + commission_pips

# Example with defaults:
# commission = (2 × 7.0 × 1.0) / 10.0 = 1.4 pips
# total_cost = 1.0 + (2 × 0.5) + 1.4 = 3.4 pips
```

**Min Edge Requirement**:
```python
TP1_distance_pips > total_cost_pips + min_edge_pips

# Default min_edge = 4.0 pips
# Example: TP1 must be > 3.4 + 4.0 = 7.4 pips minimum
```

**Why This Matters**:
- Even winning trades can be net negative after costs
- Ensures every trade has meaningful profit potential
- Accounts for broker-specific costs (spread, commission, slippage)
- Prevents low-probability-of-profit trades

**Default Cost Parameters**:
```python
COST_CONFIG = {
    "spread_pips": 1.0,                    # Typical EURUSD spread
    "slippage_pips": 0.5,                  # One-way slippage
    "commission_per_side_per_lot": 7.0,    # USD per lot per side
    "usd_per_pip_per_lot": 10.0,           # Standard lot
    "lot_size": 1.0,                       # Lots traded
    "min_edge_pips": 4.0                   # Minimum profit edge
}
```

**Example Calculations**:

**Case 1: Insufficient Edge (REJECTED)**
```
Entry: 1.08500
SL: 1.08470 (3.0 pips risk)
TP1: 1.08530 (3.0 pips reward = 1R)
TP1 distance: 3.0 pips
Total costs: 3.4 pips
Required: 3.4 + 4.0 = 7.4 pips
Result: REJECTED (3.0 < 7.4)
Reason: "Insufficient edge after costs"
```

**Case 2: Sufficient Edge (ACCEPTED)**
```
Entry: 1.08500
SL: 1.08450 (5.0 pips risk)
TP1: 1.08550 (5.0 pips reward = 1R)
TP1 distance: 5.0 pips
Total costs: 3.4 pips
Required: 3.4 + 4.0 = 7.4 pips

Wait, 5.0 < 7.4, so this would also be rejected. Let me fix:

Entry: 1.08500
SL: 1.08425 (7.5 pips risk)
TP1: 1.08575 (7.5 pips reward = 1R)
TP1 distance: 7.5 pips
Total costs: 3.4 pips
Required: 3.4 + 4.0 = 7.4 pips
Result: ACCEPTED (7.5 > 7.4)
```

## Signal Generation Decision Tree (10-Stage Pipeline)

```
START: Receive OHLCV data
  │
  ├─ STAGE 1: Bar Validation (bar_validation.py)
  │    Invalid bars → Return 422 ERROR
  │    Valid ↓
  │
  ├─ STAGE 2: Session Filter (data.py)
  │    Outside London/NY → Return HOLD (reason: "Outside trading session")
  │    Valid session ↓
  │
  ├─ STAGE 3: Trend Filter (trend_filter.py)
  │    Calculate EMA 20/50
  │    Detect trend direction
  │    Store trend info for later validation ↓
  │
  ├─ STAGE 4: S/R Detection (sr_levels.py)
  │    Detect S/R levels (score >= 60)
  │    None found → Return HOLD (reason: "No significant S/R levels")
  │    Found ↓
  │
  ├─ STAGE 5: Broken Level Filter (sr_validation.py)
  │    Check broken level cooldown (48h)
  │    All broken/cooldown → Return HOLD (reason: "All levels broken or in cooldown")
  │    Valid levels ↓
  │
  ├─ STAGE 6: Rejection Search (rejection.py)
  │    Search last 5 candles for rejection
  │    None found → Return HOLD (reason: "No rejection pattern")
  │    Found ↓
  │
  ├─ STAGE 7: Confidence Filter (main.py)
  │    Check confidence >= 0.60
  │    Too low → Return HOLD (reason: "Confidence below threshold")
  │    Sufficient confidence ↓
  │
  ├─ STAGE 8: Trend Alignment (trend_filter.py)
  │    IF confidence >= 0.75 → BYPASS (high confidence)
  │    ELSE IF signal aligns with trend → PASS
  │    ELSE → Return HOLD (reason: "Trend alignment failed")
  │    Aligned (or bypassed) ↓
  │
  ├─ STAGE 9: Signal Cooldown (main.py)
  │    Check last signal time for symbol
  │    Last signal < 2h ago → Return HOLD (reason: "Signal cooldown active")
  │    No recent signal ↓
  │
  ├─ STAGE 10: Min Edge Filter (trade_setup.py)
  │    Calculate costs (spread + slippage + commission)
  │    TP1 distance <= costs + 4 pips → Return HOLD (reason: "Insufficient edge")
  │    Sufficient edge ↓
  │
  ├─ Calculate entry, SL, TP levels
  │    ↓
  │
  └─ Return BUY/SELL signal with risk parameters
```

## Strategy Parameters (Configurable)

### S/R Detection (`SR_CONFIG`)
```python
{
    "lookback": 50,              # Bars to analyze for swings
    "swing_window": 5,           # Window for swing detection
    "min_touches": 3,            # Min touches to qualify as S/R
    "cluster_pips": 10.0,        # Pip distance to cluster levels
    "min_level_score": 60.0      # Min score to use level
}
```

### Rejection Criteria (`REJECTION_CONFIG`)
```python
{
    "min_wick_body_ratio": 1.5,  # Min wick/body ratio
    "max_distance_pips": 10.0,   # Max distance from level
    "close_position_buy": 0.60,  # Close in top 60% for BUY
    "close_position_sell": 0.40, # Close in bottom 40% for SELL
    "lookback_candles": 5        # Recent candles to check
}
```

### Risk Management (`RISK_CONFIG`)
```python
{
    "sl_pips_beyond": 10.0,      # SL distance beyond level
    "tp1_r": 1.0,                # TP1 at 1R
    "tp2_r": 2.0,                # TP2 at 2R
    "tp3_r": 3.0,                # TP3 at 3R
    "tp1_percent": 0.40,         # 40% at TP1
    "tp2_percent": 0.40,         # 40% at TP2
    "tp3_percent": 0.20,         # 20% at TP3
    "min_rr": 1.5                # Min risk:reward (not enforced)
}
```

### Trend Filter (`TREND_FILTER_CONFIG`)
```python
{
    "ema_fast": 20,                      # Fast EMA period
    "ema_slow": 50,                      # Slow EMA period
    "min_confidence_for_bypass": 0.75    # Bypass threshold for counter-trend
}
```

### Broken Level Filter (`BROKEN_LEVEL_CONFIG`)
```python
{
    "cooldown_hours": 48.0,        # Hours to wait after level break
    "break_threshold_pips": 15.0   # Pips beyond level = broken
}
```

### Confidence Filter (`CONFIDENCE_CONFIG`)
```python
{
    "min_confidence": 0.60  # Minimum confidence threshold (0.0-1.0)
}
```

### Signal Cooldown (`SIGNAL_COOLDOWN_CONFIG`)
```python
{
    "cooldown_hours": 2.0  # Hours between signals per symbol
}
```

### Min Edge Filter (`MIN_EDGE_CONFIG`)
```python
{
    "min_edge_pips": 4.0,                # Minimum profitable pips after costs
    "spread_pips": 1.0,                  # Typical spread in pips
    "slippage_pips": 0.5,                # One-way slippage in pips
    "commission_per_side_per_lot": 7.0,  # USD per lot per side
    "usd_per_pip_per_lot": 10.0,         # Standard lot pip value
    "lot_size": 1.0                      # Lots traded
}
```

## Strategy Strengths

1. **Mechanical & Objective**: No discretion required, clear rules
2. **Well-Defined Risk**: SL always known before entry
3. **Favorable Risk:Reward**: Average 1.8R per winning trade
4. **High Probability Setups**: Multiple confirmations required
5. **Adaptive**: Works across different timeframes and symbols
6. **Time-Filtered**: Only trades during optimal conditions

## Strategy Weaknesses

1. **Selective**: Many HOLD signals, requires patience
2. **Trend Dependent**: Works best in ranging or trending markets with pullbacks
3. **Requires Liquidity**: Needs active sessions for reliable execution
4. **False Breakouts**: Can get stopped out if level breaks
5. **Lagging**: Entries are conservative (at close, not wick)

## Expected Performance Characteristics

### Win Rate
- **Expected**: 50-65%
- Depends on market conditions (ranging vs trending)
- Higher win rate in ranging markets
- Lower win rate in strongly trending markets (but bigger R multiples)

### Risk:Reward
- **Average**: 1.8R per winning trade (if all TPs hit)
- **Minimum**: 1.0R (TP1 only)
- **Maximum**: 3.0R (full TP3)

### Trade Frequency
- **Low to Moderate**: 5-15 signals per day across all symbols
- Many HOLD signals (this is normal and expected)
- Quality over quantity approach

### Best Markets
- Major forex pairs (EUR/USD, GBP/USD, USD/JPY)
- Timeframes: H1, H4, D1
- Market conditions: Ranging, trending with pullbacks

### Challenging Markets
- Low liquidity pairs (wide spreads)
- Very short timeframes (< M15, too much noise)
- Strong trending markets without pullbacks
- High-impact news events (unpredictable price action)

## Backtesting Considerations

When backtesting this strategy:

1. **Use Realistic Spreads**: Account for bid/ask spread in SL/TP calculations
2. **Bar-by-Bar Simulation**: No look-ahead bias, only use data available at each candle close
3. **Session Filter**: Only include trades during valid sessions
4. **Slippage**: Add 1-2 pips slippage for market orders
5. **Partial Fills**: Simulate scaling out at each TP level
6. **Broker Conditions**: Test with your specific broker's conditions

**Note**: The included `backtest.py` is for development validation only. For production backtesting, use MT5 Strategy Tester with the provided Expert Advisor.

## Strategy Variations & Extensions

### Possible Enhancements
1. **Trend Filter**: Add 200 EMA filter to trade with trend only
2. **Volume Confirmation**: Require above-average volume on rejection candle
3. **Multiple Timeframe**: Confirm HTF S/R before taking LTF entries
4. **Breakout Mode**: Trade breakouts of strong levels instead of bounces
5. **Dynamic TP**: Adjust TP3 based on next S/R level
6. **News Filter**: Avoid trading around high-impact news events

### Parameter Tuning
All parameters in `config.py` can be optimized for specific:
- Symbols (e.g., EUR/USD vs GBP/JPY)
- Timeframes (e.g., H1 vs D1)
- Market conditions (e.g., volatile vs calm markets)
- Personal risk tolerance

## Comparison with Volarix 3

| Aspect | Volarix 3 | Volarix 4 |
|--------|-----------|-----------|
| **Approach** | Machine Learning | Rule-Based |
| **Complexity** | High (model training) | Low (pure logic) |
| **Transparency** | Black box | Fully transparent |
| **Timeframes** | Multi-TF analysis | Single-TF |
| **Dependencies** | TensorFlow, trained models | None |
| **Speed** | Moderate (model inference) | Fast (simple calculations) |
| **Maintenance** | Model retraining needed | Configuration only |
| **Explainability** | Low | High (clear reasons) |

**Why Switch to Rule-Based?**
- Easier to understand and debug
- No model training or data requirements
- More reliable in production
- Clear trade justification for every signal
