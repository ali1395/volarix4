# Parity Contract - Backtest & API Alignment

## Overview

This contract defines the **single canonical interpretation** of decision bar, execution bar, required bar count, bar ordering, filters, and costs so that `tests/backtest.py` and the MT5→DLL→API pipeline produce the same signals and (when modeled) the same fills/PnL given the same parameters.

**Purpose:** Ensure backtest results accurately predict live trading performance by eliminating implementation drift.

---

## Bar Data Contract

### Ordering
- **Bars sent to the API must be strictly chronological (oldest → newest)**, and the API must treat the last row as the newest bar.
- This ensures consistent indexing between backtest and live trading.

### Closed Bars Only (CRITICAL)
- **The API must receive only fully closed bars** for signal evaluation, and the last bar in the request is the **decision bar** (bar `i`).
- Forming bars (current bar with incomplete data) must be excluded.
- **MT5 Implementation:** Use `CopyRates(symbol, timeframe, 1, count)` (start from index 1, not 0)

### Count
- **For single-timeframe operation**, the request must include exactly `lookback_bars` closed bars (e.g., 400) for the exec timeframe.
- Insufficient bars must cause validation failure.

### Data Integrity Requirement
- **The MT5→DLL OHLCV struct must remain exactly 44 bytes** with correct packing and timestamp type to avoid nondeterminism from corrupted data.
- Use `#pragma pack(1)` in C++ and `long long timestamp` (not `long`)

---

## Decision & Execution Semantics

### Decision Time
- **A signal is evaluated strictly at bar `i` close**, using OHLCV history up to and including bar `i`.
- The decision bar is the last closed bar, not the current forming bar.

### Execution Time
- **The trade is executed at bar `i+1` open** (the new-bar moment), not at the close of bar `i`.
- This represents realistic market execution (you can't execute at the close of the decision bar).

### Entry Price Source
**Option A (Recommended - Current Implementation):**
- API returns *signal + SL/TP distances/levels* but does **not** claim a fill price.
- MT5 executes at market/new-bar open while applying SL/TP from the response.
- This matches realistic market conditions (market orders fill at next available price).

**Option B (Alternative):**
- MT5 provides an explicit `execution_price` (new-bar open / current market) to the API.
- API computes SL/TP/risk checks using that explicit execution price.
- More complex but allows API-side execution price validation.

---

## Filters & Statefulness

### Filter Parity
**Filters must match exactly** between backtest and API, including:
1. Session gating (London 3-11 EST, NY 8-22 EST)
2. Confidence gating (min_confidence threshold)
3. Trend validation (EMA 20/50)
4. Risk validation (min_edge_pips)
5. Broken-level cooldown filtering (48-hour cooldown)
6. Signal cooldown behavior (2-hour per-symbol cooldown)

**Pass/fail reasons should be comparable** between backtest and API for debugging.

### Signal Cooldown is Stateful
- **The API tracks cooldown across calls** ("cooldown activated… next signal allowed after …").
- Parity requires the backtest to emulate the same per-symbol cooldown state machine over time.
- Cooldown duration must be parameterized and identical (default: 2 hours).

---

## Costs & Rounding

### Parameter-Driven Costs
**Costs must be parameter-driven and identical** across environments, using the same configured spread/slippage/commission inputs when parity mode is enabled.

**Cost Model Parameters:**
- `spread_pips`: Broker spread (default: 1.0 pips)
- `slippage_pips`: Expected slippage per side (default: 0.5 pips)
- `commission_per_side_per_lot`: USD commission (default: 7.0)
- `usd_per_pip_per_lot`: Pip value (default: 10.0)
- `lot_size`: Trade size for commission calculation (default: 1.0)

### Deterministic Rounding Rules
- **Any rounding (prices/levels/pips) must be explicitly defined** and applied identically in backtest and API before comparisons are made.
- Floating-point comparisons should use appropriate tolerances (e.g., ±0.00001 for prices, ±0.1 for pips).

---

## MT5 Implementation - Closed Bars Only

### Problem (Before Fix)

**Issue:** MT5 EA was sending a **forming bar** as the last bar in the payload:
- EA triggers on `IsNewBar()` when a new bar opens
- Used `CopyRates(symbol, timeframe, 0, count)` which includes index 0 (current bar)
- Index 0 at bar open = forming bar with only 1 tick (unreliable OHLC)
- Last bar often had `open == close` (symptom of forming bar)

**Impact:**
- API received different bar states than backtest
- Backtest uses only closed bars → MT5 sent forming + closed bars
- Non-deterministic: same timestamp yielded different results depending on when API was called
- Signals generated on partially-formed bars (unrealistic)

### Root Cause

```mql5
// BEFORE (WRONG):
int copied = CopyRates(SymbolToCheck, Timeframe, 0, LookbackBars, rates);
//                                                 ^ index 0 = current bar (forming)
```

**MQL5 Indexing:**
- Index 0 = current bar (forming when new bar just opened)
- Index 1 = previous bar (fully closed)
- Index N = N bars ago (all closed)

**When `IsNewBar()` triggers:**
- New bar just opened
- Index 0 has only opening tick → unreliable for signal generation
- Index 1 is the last CLOSED bar → this is what we need

---

### Solution (CRITICAL FIX)

**File:** `mt5_integration/volarix4.mq5:224`

```mql5
// AFTER (CORRECT):
int copied = CopyRates(SymbolToCheck, Timeframe, 1, LookbackBars, rates);
//                                                 ^ index 1 = last CLOSED bar
```

**Change:** Start from index 1 instead of index 0
**Result:** Skip the forming bar, send only closed bars

---

### Validation Added

#### 1. Bar Ordering & Uniqueness

**Code:** `volarix4/utils/bar_validation.py:57-156`

Validates:
- ✅ No `time == 0` (invalid bars)
- ✅ Strictly increasing timestamps (oldest → newest)
- ✅ No duplicates
- ✅ Timeframe alignment (each bar delta is multiple of timeframe period)
- ✅ Weekend/holiday gaps allowed (up to 168 periods = 1 week)

**Example:**
```
H1 timeframe → each bar should be 3600 seconds apart
If bar[i] time = 1000, bar[i+1] time should be ≥ 1000 + 3600
Weekends: gap of 48-55 hours (49-55 periods) is allowed
```

#### 2. Minimum Bar Count

**Code:** `volarix4/utils/bar_validation.py:98-103`

Checks:
- Minimum 200 bars (default, configurable)
- Required for lookback (EMA calculation, S/R detection)

#### 3. Bar Validation Summary Logging

**Code:** `volarix4/utils/bar_validation.py:178-210`

**Output:**
```
======================================================================
BAR VALIDATION SUMMARY (Parity Contract)
======================================================================
Symbol: EURUSD
Timeframe: H1 (3600 seconds)
Bar count: 400
First bar time: 2025-01-10 12:00:00 (timestamp: 1736510400)
Last bar time: 2025-02-10 15:00:00 (timestamp: 1739185200)
Decision bar time: 2025-02-10 15:00:00 (timestamp: 1739185200)
Decision bar close: 1.08520
Time span: 2674800 seconds (743.0 hours)
Expected bars (if no gaps): 744
Gap detected: 344 bars missing (weekends/holidays expected)
Validation: PASSED ✅
======================================================================
```

**What to look for:**
- ✅ `Validation: PASSED ✅` - All checks passed
- ✅ Bar count matches requested (400 bars)
- ✅ Gap detection shows missing bars due to weekends (expected)

---

## Parity Contract Compliance

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| **Closed bars only** | ✅ **ENFORCED** | `CopyRates(symbol, tf, 1, count)` in MT5 EA |
| **Strictly increasing timestamps** | ✅ **VALIDATED** | `bar_validation.py:114-126` |
| **No duplicates** | ✅ **VALIDATED** | Same check as above |
| **No time == 0** | ✅ **VALIDATED** | `bar_validation.py:107-112` |
| **Timeframe alignment** | ✅ **VALIDATED** | `bar_validation.py:128-155` |
| **Minimum bar count** | ✅ **VALIDATED** | `bar_validation.py:98-103` |
| **Weekend gap tolerance** | ✅ **ENFORCED** | `max_gap_multiplier=168` (1 week) |
| **Oldest → newest ordering** | ✅ **ENFORCED** | MT5 CopyRates natural order |

---

## Expected Behavior

### Consecutive Requests (N=400, H1 timeframe)

**Scenario:** EA calls API every hour on new bar

**Before Fix:**
```
Request 1 (12:00): Last bar = 12:00 (forming, age = 5 sec)
Request 2 (13:00): Last bar = 13:00 (forming, age = 5 sec)
                   ^ Same forming bar behavior every time
```

**After Fix:**
```
Request 1 (12:00): Last bar = 11:00 (closed, age = 3605 sec)
Request 2 (13:00): Last bar = 12:00 (closed, age = 3605 sec)
                   ^ Advanced by exactly 1 closed bar
```

**Difference:**
- ✅ Last bar advances by exactly 1 bar (3600 seconds) between requests
- ✅ Last bar is always closed (age ≥ 3600 seconds)
- ✅ No forming bar signature (open ≠ close, proper OHLC range)

---

## API Log Changes

### Before (with forming bar)

```
[DEBUG] Last bar [399]: time=1739188800, open=1.08520, close=1.08520
                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                          open == close (forming bar!)
```

### After (closed bars only)

```
[DEBUG] Last bar [399]: time=1739185200, open=1.08495, close=1.08537
                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                          open ≠ close (closed bar!)
```

**Indicator of success:**
- API logs: `Bars with time=0: 0 out of 400` ✅
- Timestamps strictly increasing ✅
- Last bar has proper OHLC range (not open == close) ✅

---

## Testing Checklist

### Manual Test

1. **Attach EA** to H1 chart
2. **Wait for new bar** to trigger
3. **Check MT5 Experts tab** for validation output
4. **Verify:**
   - [ ] Bar count matches requested (400 bars)
   - [ ] `Validation: PASSED ✅`
   - [ ] No errors in bar validation
5. **Check API logs:**
   - [ ] `Bars with time=0: 0 out of 400`
   - [ ] Last bar has `open ≠ close` (not forming)
6. **Wait 1 hour** for next bar
7. **Verify last bar advanced by exactly 1 bar** (3600 seconds for H1)

### Backtest Comparison

**Before parity fix:**
- Backtest signals at closed bars
- MT5 signals on forming bars
- Results don't match

**After parity fix:**
- Backtest signals at closed bars ✅
- MT5 signals at closed bars ✅
- Results should closely match (within tick model differences)

---

## Troubleshooting

### "Excessive gap" Error

**Cause:** Weekend/holiday gap exceeds maximum allowed gap (168 periods = 1 week)
**Solution:** This is usually a data issue. Check:
1. MT5 history is complete: Tools → History Center → Delete & Reload
2. If legitimate long gap (extended holiday), increase `max_gap_multiplier` in `bar_validation.py`

### "Bars not strictly increasing" Error

**Cause:** MT5 data corruption or history gaps
**Solution:**
1. Rebuild MT5 history: Tools → History Center → Delete & Reload
2. Restart MT5
3. Reattach EA

### "Insufficient bars" Error

**Cause:** Not enough historical data available
**Solution:**
1. Download more history: Tools → History Center → Download
2. Reduce `LookbackBars` parameter (not recommended - affects strategy)

---

## Migration Notes

### Existing Users

**If you're already using the EA:**
1. **Update EA file** from repository
2. **Recompile** in MetaEditor
3. **Reattach to chart**
4. **Verify logs** show `Validation: PASSED ✅` on next bar

**Impact:**
- Signals may arrive 1 bar later (now waits for bar close)
- Results will match backtest more closely
- May see different signals (fewer false signals on forming bars)

### Backtest Users

**No changes needed** - backtest already uses closed bars only

**Benefit:** MT5 live trading now matches your backtest results!

---

## Technical Details

### MQL5 CopyRates Behavior

```mql5
// Signature
int CopyRates(
   string           symbol_name,     // symbol name
   ENUM_TIMEFRAMES  timeframe,       // timeframe
   int              start_pos,       // start position (0 = current bar)
   int              count,           // number of bars to copy
   MqlRates         rates_array[]    // target array
);
```

**Indexing:**
- `start_pos = 0`: Current bar (forming if new bar just opened)
- `start_pos = 1`: Previous bar (closed)
- `start_pos = N`: N bars ago

**Array order:** Oldest → newest
- `rates[0]` = oldest bar
- `rates[count-1]` = newest bar

### Our Implementation

```mql5
CopyRates(SymbolToCheck, Timeframe, 1, LookbackBars, rates);
//                                   ^
//                                   Skip current bar (index 0)
//                                   Start from last closed bar (index 1)
```

**Result:**
- `rates[0]` = bar at index 1 (LookbackBars bars ago, closed)
- `rates[399]` = bar at index 400 (last closed bar, NOT current forming bar)

---

## References

- **EA Code:** `mt5_integration/volarix4.mq5:224`
- **Bar Validation:** `volarix4/utils/bar_validation.py`
- **Backtest Code:** `tests/backtest.py` (uses closed bars)
- **API Endpoint:** `volarix4/api/main.py` (receives all bars)
- **Parity Tests:** `tests/test_backtest_api_parity.py`

---

## Summary of Changes

| File | Line | Change | Reason |
|------|------|--------|--------|
| `volarix4.mq5` | 224 | `CopyRates(..., 1, ...)` | Skip forming bar, send closed bars only |
| `bar_validation.py` | 57-176 | Comprehensive validation | Check ordering, uniqueness, gaps, count |
| `bar_validation.py` | 62 | `max_gap_multiplier=168` | Allow weekend/holiday gaps (1 week) |
| `bar_validation.py` | 178-210 | Validation logging | Debug output for troubleshooting |

---

**Implementation Date:** 2025-12-29
**Status:** ✅ **COMPLETE**
**Impact:** 🔴 **CRITICAL** - Required for backtest parity
