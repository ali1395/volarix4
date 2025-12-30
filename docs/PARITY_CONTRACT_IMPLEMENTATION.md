# Parity Contract Implementation: Closed Bars Only

## Summary

**CRITICAL FIX:** MT5 EA now sends **ONLY closed bars** to the API, ensuring deterministic results matching the offline backtest.

---

## Problem Statement

### Before Fix

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

## Solution

### Fix Applied

**File:** `mt5_integration/volarix4.mq5:311`

```mql5
// AFTER (CORRECT):
int copied = CopyRates(SymbolToCheck, Timeframe, 1, LookbackBars, rates);
//                                                 ^ index 1 = last CLOSED bar
```

**Change:** Start from index 1 instead of index 0
**Result:** Skip the forming bar, send only closed bars

---

## Validation Added

### 1. Bar Ordering & Uniqueness

**Code:** `volarix4.mq5:329-357`

Validates:
- ✅ No `time == 0` (invalid bars)
- ✅ Strictly increasing timestamps (oldest → newest)
- ✅ No duplicates
- ✅ Timeframe alignment (each bar delta is multiple of timeframe period)

**Example:**
```
H1 timeframe → each bar should be 3600 seconds apart
If bar[i] time = 1000, bar[i+1] time should be ≥ 1000 + 3600
```

### 2. Closed Bar Check

**Code:** `volarix4.mq5:359-373`

Checks:
- Last bar age ≥ timeframe period
- Age = `current_server_time - last_bar_time`
- For H1: last bar should be at least 3600 seconds old

**Logic:**
```mql5
datetime last_bar_time = rates[copied-1].time;
datetime current_server_time = TimeCurrent();
long last_bar_age_seconds = (long)current_server_time - (long)last_bar_time;

bool last_bar_closed = (last_bar_age_seconds >= timeframe_seconds);
```

### 3. Debug Logging

**Code:** `volarix4.mq5:375-390`

**Output:**
```
=== BAR VALIDATION (Parity Contract) ===
  Bars copied: 400 (requested: 400)
  First bar [0]: time=2024-12-25 12:00:00 (1735128000)
  Last bar [399]: time=2025-02-10 15:00:00 (1739185200)
  Delta last 2 bars: 3600 seconds (expected: 3600)
  Last bar age: 3610 sec (timeframe: 3600 sec) - Closed: YES
  Bars validation: PASSED
========================================
```

**What to look for:**
- ✅ `Closed: YES` - Last bar is fully closed
- ✅ `Delta last 2 bars` matches timeframe period
- ✅ `Bars validation: PASSED` - All checks passed

---

## Parity Contract Compliance

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| **Closed bars only** | ✅ **FIXED** | `CopyRates(symbol, tf, 1, count)` |
| **Strictly increasing timestamps** | ✅ **VALIDATED** | Loop check at line 329-357 |
| **No duplicates** | ✅ **VALIDATED** | Same loop check |
| **No time == 0** | ✅ **VALIDATED** | Check at line 332-336 |
| **Timeframe alignment** | ✅ **VALIDATED** | Check at line 351-355 |
| **Last bar closed** | ✅ **VALIDATED** | Age check at line 359-373 |
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
- API continues showing: `Bars with time=0: 0 out of 400` ✅
- Timestamps strictly increasing ✅
- Last bar has proper OHLC range (not open == close) ✅

---

## Testing Checklist

### Manual Test

1. **Attach EA** to H1 chart
2. **Wait for new bar** to trigger
3. **Check MT5 Experts tab** for validation output
4. **Verify:**
   - [ ] `Closed: YES`
   - [ ] `Delta last 2 bars: 3600`
   - [ ] `Bars validation: PASSED`
5. **Check API logs:**
   - [ ] `Bars with time=0: 0 out of 400`
   - [ ] Last bar has `open ≠ close` (not forming)
6. **Wait 1 hour** for next bar
7. **Verify last bar advanced by exactly 1 bar** (3600 seconds)

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

### "Last bar may be forming" Warning

**Cause:** Bar age < timeframe period
**Solution:** This is expected if EA is triggered very early in the bar (MT5 timing quirk)
**Action:** Check if bar age is close to timeframe (e.g., 3595 sec for H1) - likely OK

### "Bars not strictly increasing" Error

**Cause:** MT5 data corruption or history gaps
**Solution:**
1. Rebuild MT5 history: Tools → History Center → Delete & Reload
2. Restart MT5
3. Reattach EA

### "Bar validation failed" Error

**Cause:** Invalid bars in MT5 history
**Impact:** EA aborts API call (safe behavior)
**Solution:** Fix MT5 history as above

---

## Migration Notes

### Existing Users

**If you're already using the EA:**
1. **Update EA file** from repository
2. **Recompile** in MetaEditor
3. **Reattach to chart**
4. **Verify logs** show `Closed: YES` on next bar

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

- **Parity Contract:** `docs/Parity_Contract.md`
- **EA Code:** `mt5_integration/volarix4.mq5:308-396`
- **Backtest Code:** `tests/backtest.py:751-763` (uses closed bars)
- **API Endpoint:** `volarix4/api/main.py:298-315` (receives all bars)

---

## Summary of Changes

| File | Line | Change | Reason |
|------|------|--------|--------|
| `volarix4.mq5` | 311 | `CopyRates(..., 1, ...)` | Skip forming bar, send closed bars only |
| `volarix4.mq5` | 319-323 | Count validation | Ensure exactly N bars copied |
| `volarix4.mq5` | 329-357 | Ordering validation | Check strictly increasing, no duplicates, alignment |
| `volarix4.mq5` | 359-373 | Closed bar check | Verify last bar age ≥ timeframe |
| `volarix4.mq5` | 375-390 | Debug logging | Log validation results for debugging |
| `volarix4.mq5` | 392-396 | Abort on failure | Don't call API if validation fails |

---

**Implementation Date:** 2025-01-29
**Status:** ✅ **COMPLETE**
**Impact:** 🔴 **CRITICAL** - Required for backtest parity
