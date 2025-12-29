# SL/TP Entry Mismatch Fix - Implementation Summary

## Problem Identified

The backtester had a critical bug where:
1. **SL/TP were calculated using `rejection['entry']`** (the close of the rejection candle)
2. **But trades were opened at `entry_bar['open']`** (the open of the next bar)
3. This mismatch could cause TPs to be on the wrong side of the actual entry price
4. Leading to impossible cases like `exit_reason="All TPs hit"` with negative `pnl_after_costs`

## Fixes Implemented

### 1. Recompute SL/TP Using Actual Entry Price
**File:** `tests/backtest.py` (lines 837-846)

**Before:**
```python
# Calculate trade setup
trade_params = calculate_sl_tp(
    entry=rejection['entry'],  # ❌ Wrong! Using rejection candle close
    level=rejection['level'],
    direction=direction,
    sl_pips_beyond=10.0,
    pip_value=pip_value
)

# Create trade (enter on next bar open)
next_bar_idx = i + 1
if next_bar_idx < len(df):
    entry_bar = df.iloc[next_bar_idx]
    open_trade = Trade(
        entry=entry_bar['open'],  # ❌ Different entry price!
        sl=trade_params['sl'],
        ...
    )
```

**After:**
```python
# Create trade (enter on next bar open)
next_bar_idx = i + 1
if next_bar_idx < len(df):
    entry_bar = df.iloc[next_bar_idx]
    actual_entry = entry_bar['open']

    # Calculate trade setup using ACTUAL entry price (next bar open)
    trade_params = calculate_sl_tp(
        entry=actual_entry,  # ✅ Correct! Using actual entry
        level=rejection['level'],
        direction=direction,
        sl_pips_beyond=10.0,
        pip_value=pip_value
    )

    # Sanity check before opening trade
    if not levels_sane(...):
        filter_rejections["invalid_geometry"] += 1
        continue

    # Create trade with validated parameters
    open_trade = Trade(
        entry=actual_entry,  # ✅ Same entry price!
        sl=trade_params['sl'],
        ...
    )
```

### 2. Added Sanity Guard Function
**File:** `tests/backtest.py` (lines 588-606)

```python
def levels_sane(entry: float, sl: float, tp1: float, tp2: float, tp3: float, direction: str) -> bool:
    """
    Sanity check for SL/TP geometry.

    For BUY: sl < entry < tp1 < tp2 < tp3
    For SELL: tp3 < tp2 < tp1 < entry < sl

    Returns:
        True if geometry is valid, False otherwise
    """
    direction = direction.upper()

    if direction == "BUY":
        return sl < entry < tp1 < tp2 < tp3
    elif direction == "SELL":
        return tp3 < tp2 < tp1 < entry < sl
    else:
        return False
```

**Usage:** (lines 848-860)
```python
# Sanity check: validate SL/TP geometry
if not levels_sane(
    entry=actual_entry,
    sl=trade_params['sl'],
    tp1=trade_params['tp1'],
    tp2=trade_params['tp2'],
    tp3=trade_params['tp3'],
    direction=direction
):
    # Invalid geometry - skip this trade
    filter_rejections["invalid_geometry"] += 1
    signals_generated["HOLD"] += 1
    continue
```

### 3. Added Invalid Geometry Filter Counter
**File:** `tests/backtest.py` (lines 713-717)

```python
filter_rejections = {
    "confidence": 0,
    "broken_level": 0,
    "invalid_geometry": 0  # ✅ New counter
}
```

**Display:** (line 1148)
```python
print(f"{'Invalid geometry rejections':<30} {filter_rejections['invalid_geometry']:>10}")
```

### 4. Hardened calculate_sl_tp() Direction Validation
**File:** `volarix4/core/trade_setup.py` (lines 27-30)

**Before:**
```python
if direction == 'BUY':
    # BUY logic
else:  # SELL
    # ❌ Any non-BUY direction goes here, even typos!
    # SELL logic
```

**After:**
```python
# Validate direction parameter
direction = direction.upper()
if direction not in ("BUY", "SELL"):
    raise ValueError(f"Invalid direction '{direction}'. Must be 'BUY' or 'SELL'.")

if direction == 'BUY':
    # BUY logic
else:  # SELL
    # ✅ Now guaranteed to be "SELL"
    # SELL logic
```

### 5. Updated Context Pip Calculations
**File:** `tests/backtest.py` (lines 883-889)

Already using `actual_entry` for consistency:
```python
# Calculate SL/TP in pips (using actual_entry)
if direction == "BUY":
    open_trade.sl_pips = (actual_entry - trade_params['sl']) / pip_value
    open_trade.tp1_pips = (trade_params['tp1'] - actual_entry) / pip_value
else:  # SELL
    open_trade.sl_pips = (trade_params['sl'] - actual_entry) / pip_value
    open_trade.tp1_pips = (actual_entry - trade_params['tp1']) / pip_value
```

## Impact

### Before Fix:
```
Entry scenarios that could occur:
1. Rejection candle closes at 1.08520
2. Next bar opens at 1.08550 (30 pip gap up)
3. SL/TP calculated from 1.08520 (rejection close)
4. Trade opened at 1.08550 (next bar open)

For a BUY trade:
- Entry: 1.08550
- TP1 calculated from 1.08520: might be 1.08570 (50 pips from 1.08520)
- But from actual entry 1.08550, TP1 is only 20 pips away!
- TP3 might even be BELOW entry if gap is large enough!

Result: "All TPs hit" with negative PnL ❌
```

### After Fix:
```
Entry scenarios now correctly handled:
1. Rejection candle closes at 1.08520
2. Next bar opens at 1.08550 (30 pip gap up)
3. SL/TP calculated from 1.08550 (actual entry) ✅
4. Trade opened at 1.08550 (same entry)

For a BUY trade:
- Entry: 1.08550
- TP1: 1.08600 (50 pips from 1.08550) ✅
- TP2: 1.08650 (100 pips from 1.08550) ✅
- TP3: 1.08700 (150 pips from 1.08550) ✅
- SL: 1.08490 (60 pips below entry) ✅

Geometry validation:
- BUY: SL (1.08490) < Entry (1.08550) < TP1 (1.08600) < TP2 (1.08650) < TP3 (1.08700) ✅

Result: Correct TP/SL relationships, valid PnL calculations ✅
```

## Expected Behavior Changes

1. **"All TPs hit" with negative PnL** should now be extremely rare
   - Only possible if costs (spread + commission + slippage) exceed profit
   - Not because TP is geometrically behind entry

2. **Invalid geometry rejections** will be tracked
   - Shows how many trades were skipped due to sanity check failures
   - Useful for debugging extreme market conditions (large gaps)

3. **Direction validation errors** will raise exceptions early
   - Prevents silent bugs from typos or incorrect direction values
   - Fails fast with clear error message

## Verification

To verify the fix is working:

1. **Check filter statistics:**
   ```
   --- FILTER STATISTICS ---
   Confidence rejections                     25
   Broken level rejections                   12
   Invalid geometry rejections                0  ← Should be 0 or very small
   Signals generated (BUY/SELL)            45/38
   ```

2. **Inspect trades CSV:**
   - Check that all BUY trades have: `sl < entry_after_costs < tp1 < tp2 < tp3`
   - Check that all SELL trades have: `tp3 < tp2 < tp1 < entry_after_costs < sl`

3. **Review exit reasons:**
   - "TP1 hit" → should always have positive PnL (after costs might be negative due to fees)
   - "TP2 hit" → should have even better PnL
   - "TP3 hit" → should have best PnL
   - "All TPs hit" → should ALWAYS have positive gross profit (costs might make final PnL negative)

## Files Modified

1. **tests/backtest.py**
   - Added `levels_sane()` helper function
   - Added "invalid_geometry" filter counter
   - Fixed SL/TP calculation to use actual entry
   - Added sanity check before opening trades
   - Updated filter statistics display

2. **volarix4/core/trade_setup.py**
   - Added direction validation in `calculate_sl_tp()`
   - Raises ValueError for invalid directions

## Backward Compatibility

✅ **No breaking changes to output format**
- All existing metrics remain the same
- CSV structure unchanged
- Only added new "invalid_geometry" filter counter

✅ **Behavior changes are bug fixes**
- Trades now correctly calculate SL/TP from actual entry
- Invalid geometries are now properly rejected
- Direction validation prevents silent errors

## Testing Recommendations

1. **Run a full walk-forward analysis:**
   ```python
   python -m tests.backtest
   ```

2. **Check for invalid geometry rejections:**
   - If count is 0: Perfect! No entry/SL/TP mismatches
   - If count is small (<5% of trades): Normal, likely due to gaps
   - If count is large (>10% of trades): Investigate gap behavior

3. **Verify TP/SL relationships in CSV:**
   ```python
   import pandas as pd

   df = pd.read_csv('./outputs/trades_EURUSD_H1_20251228_143052.csv')

   # Check BUY trades
   buy_trades = df[df['direction'] == 'BUY']
   assert all(buy_trades['sl'] < buy_trades['entry_after_costs'])
   assert all(buy_trades['entry_after_costs'] < buy_trades['tp1'])
   assert all(buy_trades['tp1'] < buy_trades['tp2'])
   assert all(buy_trades['tp2'] < buy_trades['tp3'])

   # Check SELL trades
   sell_trades = df[df['direction'] == 'SELL']
   assert all(sell_trades['tp3'] < sell_trades['tp2'])
   assert all(sell_trades['tp2'] < sell_trades['tp1'])
   assert all(sell_trades['tp1'] < sell_trades['entry_after_costs'])
   assert all(sell_trades['entry_after_costs'] < sell_trades['sl'])
   ```

## Summary

✅ **Fixed:** SL/TP now calculated from actual entry (next bar open)
✅ **Added:** Sanity check to validate TP/SL geometry before opening trades
✅ **Hardened:** Direction validation in calculate_sl_tp()
✅ **Tracked:** Invalid geometry rejections in filter statistics

**Result:** "All TPs hit but negative PnL" bug eliminated. SL/TP relationships are now always geometrically correct relative to actual entry price.
