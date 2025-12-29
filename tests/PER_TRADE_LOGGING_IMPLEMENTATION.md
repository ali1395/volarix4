# Per-Trade Logging and Bucket Diagnostics - Implementation Guide

## Overview

I've added the foundation for comprehensive per-trade logging with context and bucket diagnostics. Here's what's been implemented and what needs to be integrated:

## ✅ Completed

### 1. **Trade Class Extended** (lines 32-84)

Added new fields to store trade context:
```python
# Context at entry (to be populated by caller)
self.rejection_confidence = None
self.level_price = None
self.level_type = None  # 'support' or 'resistance'
self.sl_pips = None
self.tp1_pips = None
self.hour_of_day = None
self.day_of_week = None
self.atr_pips_14 = None
self.exit_bar_time = None  # Set on exit
```

### 2. **Utility Functions Added** (lines 328-514)

**calculate_atr_pips()**: Calculates ATR in pips for last 14 bars
```python
atr_pips = calculate_atr_pips(df, period=14, pip_value=0.0001)
```

**trades_to_dataframe()**: Converts Trade list to DataFrame
```python
trades_df = trades_to_dataframe(completed_trades)
```

**print_bucket_diagnostics()**: Prints detailed bucket analysis
- Direction buckets (BUY vs SELL)
- Hour of day (Asian/London/NY)
- ATR quartiles (low/med/high volatility)
- Confidence bins (<0.6, 0.6-0.7, ≥0.7)

## 🔧 Integration Required

### Step 1: Populate Trade Context in run_backtest()

When creating a trade in the backtest loop, populate the context fields:

**Location:** In run_backtest(), where trades are created (search for `Trade(` constructor calls)

**Add after creating the trade:**
```python
# Create trade (existing code)
trade = Trade(
    entry_time=df.iloc[i]['time'],
    direction=signal_dict['direction'],
    entry=df.iloc[i]['close'],
    sl=signal_dict['sl'],
    tp1=signal_dict['tp1'],
    tp2=signal_dict['tp2'],
    tp3=signal_dict['tp3'],
    pip_value=pip_value,
    spread_pips=spread_pips,
    slippage_pips=slippage_pips,
    commission_per_side_per_lot=commission_per_side_per_lot,
    lot_size=lot_size
)

# NEW: Populate context fields
trade.rejection_confidence = signal_dict.get('confidence', None)
trade.level_price = signal_dict.get('level_price', None)
trade.level_type = signal_dict.get('level_type', None)

# Calculate SL/TP in pips
if signal_dict['direction'] == "BUY":
    trade.sl_pips = (trade.entry_raw - signal_dict['sl']) / pip_value
    trade.tp1_pips = (signal_dict['tp1'] - trade.entry_raw) / pip_value
else:  # SELL
    trade.sl_pips = (signal_dict['sl'] - trade.entry_raw) / pip_value
    trade.tp1_pips = (trade.entry_raw - signal_dict['tp1']) / pip_value

# Extract time context
entry_dt = df.iloc[i]['time']
trade.hour_of_day = entry_dt.hour
trade.day_of_week = entry_dt.dayofweek  # 0=Monday, 6=Sunday

# Calculate ATR at entry (using data up to current bar)
df_for_atr = df.iloc[:i+1]
trade.atr_pips_14 = calculate_atr_pips(df_for_atr, period=14, pip_value=pip_value)
```

### Step 2: Modify run_backtest() to Return trades_df

**Location:** At the end of run_backtest(), before returning results

**Add:**
```python
# Convert trades to DataFrame
trades_df = trades_to_dataframe(completed_trades)

# Save to CSV if requested
import os
from datetime import datetime

output_dir = "./outputs"
os.makedirs(output_dir, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_filename = f"{output_dir}/trades_{symbol}_{timeframe}_{timestamp}.csv"

if len(trades_df) > 0:
    trades_df.to_csv(csv_filename, index=False)
    if verbose:
        print(f"\n✓ Saved {len(trades_df)} trades to {csv_filename}")

# Add trades_df to results dictionary
results['trades_df'] = trades_df

return results
```

### Step 3: Get level_price and level_type from Signal

The signal generation needs to return level information. Modify where signals are generated:

**In volarix4/core/rejection.py** or wherever rejection is detected, ensure the returned dict includes:
```python
return {
    'direction': direction,
    'sl': sl,
    'tp1': tp1,
    'tp2': tp2,
    'tp3': tp3,
    'confidence': rejection_confidence,
    'level_price': level['level'],  # ADD THIS
    'level_type': level['type']     # ADD THIS ('support' or 'resistance')
}
```

### Step 4: Add Bucket Diagnostics to Walk-Forward

**Location:** In run_walk_forward(), after each test split completes

**Find:** The section where Monte Carlo is called (around line 1300-1340)

**Add after Monte Carlo section:**
```python
# Bucket diagnostics for test trades
test_trades = test_result.get('trades', [])
if len(test_trades) > 0:
    print_bucket_diagnostics(test_trades, bucket_name=f"SPLIT {split_idx + 1} TEST")
```

## 📊 Expected Output

### Bucket Diagnostics Example

```
======================================================================
[SPLIT 1 TEST] BUCKET DIAGNOSTICS
======================================================================

1. DIRECTION BUCKETS:
Bucket          Trades   Net PnL      PF         Avg Win    Avg Loss
----------------------------------------------------------------------
BUY             8        125.3        2.15       45.2       18.5
SELL            7        -32.5        0.75       28.3       42.1

2. HOUR OF DAY BUCKETS:
Bucket          Trades   Net PnL      PF         Avg Win    Avg Loss
----------------------------------------------------------------------
Asian (0-7)     2        15.2         1.25       35.0       20.0
London (8-15)   10       95.8         2.50       48.5       15.2
NY (16-23)      3        -17.7        0.65       22.0       38.5

3. ATR VOLATILITY BUCKETS:
Bucket          Trades   Net PnL      PF         Avg Win    Avg Loss
----------------------------------------------------------------------
Low ATR         5        85.3         3.20       52.0       12.5
Medium ATR      7        45.2         1.55       38.0       22.0
High ATR        3        -37.8        0.55       25.0       48.0

4. CONFIDENCE BUCKETS:
Bucket          Trades   Net PnL      PF         Avg Win    Avg Loss
----------------------------------------------------------------------
<0.6            3        -25.5        0.60       18.0       35.0
0.6-0.7         8        52.3         1.80       42.0       20.0
≥0.7            4        98.5         4.25       58.0       10.5
======================================================================
```

### CSV Output Example

**File:** `./outputs/trades_EURUSD_H1_20251228_143052.csv`

| entry_bar_time | exit_bar_time | direction | entry_raw | exit_price | pnl_after_costs | rejection_confidence | level_price | level_type | sl_pips | tp1_pips | hour_of_day | day_of_week | atr_pips_14 |
|----------------|---------------|-----------|-----------|------------|-----------------|---------------------|-------------|------------|---------|----------|-------------|-------------|-------------|
| 2024-12-20 09:00 | 2024-12-20 15:00 | BUY | 1.08500 | 1.08650 | 12.5 | 0.75 | 1.08450 | support | 15.0 | 40.0 | 9 | 4 | 25.3 |
| 2024-12-20 14:00 | 2024-12-20 18:00 | SELL | 1.09000 | 1.08850 | -8.2 | 0.62 | 1.09050 | resistance | 18.0 | 35.0 | 14 | 4 | 28.7 |

## 🎯 Benefits

### 1. **Detailed Trade Analysis**
- See exact entry/exit context for every trade
- Understand which conditions produce best results

### 2. **Pattern Discovery**
- BUY vs SELL performance differences
- Best trading hours (Asian vs London vs NY)
- Optimal volatility conditions (low/med/high ATR)
- Confidence threshold effectiveness

### 3. **Strategy Refinement**
- Filter trades by hour if one session performs poorly
- Adjust position size based on volatility (ATR)
- Increase min_confidence if low confidence trades lose

### 4. **Audit Trail**
- Complete CSV of all trades for external analysis
- Can be imported into Excel, Python, R
- Verifiable backtest results

## 🔍 Analysis Examples

### Example 1: Time of Day Discovery

```
2. HOUR OF DAY BUCKETS:
London (8-15)   10       +95.8        2.50
NY (16-23)      3        -17.7        0.65
```

**Insight:** Strategy performs much better during London session
**Action:** Add hour filter to only trade 8:00-15:00 EST

### Example 2: Volatility Preference

```
3. ATR VOLATILITY BUCKETS:
Low ATR         5        +85.3        3.20
High ATR        3        -37.8        0.55
```

**Insight:** Strategy works best in low volatility
**Action:** Add ATR filter - only trade when ATR < median

### Example 3: Confidence Validation

```
4. CONFIDENCE BUCKETS:
<0.6            3        -25.5        0.60
≥0.7            4        +98.5        4.25
```

**Insight:** High confidence trades perform much better
**Action:** Increase min_confidence from 0.65 to 0.70

### Example 4: Direction Bias

```
1. DIRECTION BUCKETS:
BUY             8        +125.3       2.15
SELL            7        -32.5        0.75
```

**Insight:** BUY trades much more profitable than SELL
**Action:** Consider trading BUY signals only, or reduce SELL position size

## 📝 Implementation Checklist

- [x] Trade class extended with context fields
- [x] ATR calculation function added
- [x] trades_to_dataframe() function added
- [x] print_bucket_diagnostics() function added
- [ ] Populate Trade context in run_backtest() loop
- [ ] Modify signal generation to return level_price/level_type
- [ ] Add trades_df to run_backtest() return value
- [ ] Add CSV saving to run_backtest()
- [ ] Add bucket diagnostics call in walk-forward

## 🚀 Quick Start

1. **Populate trade context** in the backtest loop (Step 1)
2. **Modify signal generation** to include level info (Step 3)
3. **Return trades_df** from run_backtest (Step 2)
4. **Call bucket diagnostics** in walk-forward (Step 4)

Once integrated, you'll have complete trade-level visibility with automated bucket analysis after every test split!
