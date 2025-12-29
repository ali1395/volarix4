# MT5 Integration Guide - Volarix 4

Complete guide for integrating Volarix 4 API with MetaTrader 5 with **backtest parity** support.

## Overview

The MT5 integration now uses **direct WebRequest** to call the API with full strategy parameters matching `tests/backtest.py`:
1. **volarix4.mq5** - Expert Advisor that calls the API via WebRequest and executes trades
2. **Backtest Parity Mode** - Forces best backtest parameters for comparable results

**DEPRECATED:** The previous DLL-based integration (Volarix4Bridge.dll) is no longer needed.

## Architecture

```
MT5 Chart / Strategy Tester
    ↓
volarix4.mq5 (Expert Advisor)
    ↓ HTTP POST (with strategy parameters)
Volarix 4 API (FastAPI)
    ↓ (applies same filters as tests/backtest.py)
Response (Signal + SL/TP)
    ↓
volarix4.mq5 executes trade
```

## Prerequisites

- MetaTrader 5 (64-bit)
- Volarix 4 API running on `localhost:8000`
- No DLL compilation needed (now uses native WebRequest)

## Backtest Parity Mode

**NEW:** The EA now supports **Backtest Parity Mode** to make MT5 Strategy Tester results comparable to `tests/backtest.py`.

### How It Works

When `BacktestParityMode = true` (default), the EA:
1. **Forces** best backtest parameters regardless of input values:
   - `min_confidence = 0.60`
   - `broken_level_cooldown_hours = 48.0`
   - `broken_level_break_pips = 15.0`
   - `min_edge_pips = 4.0`
   - Standard cost model: spread=1.0, slippage=0.5, commission=$7/lot
2. **Logs** all active parameters to MT5 Experts tab on startup
3. **Sends** these parameters to the API in every request
4. **Ensures** API applies same filters as Python backtest

### Why Use Backtest Parity Mode?

- **Comparable results**: MT5 Strategy Tester will use same strategy logic as `tests/backtest.py`
- **Apples-to-apples**: You can compare win rate, profit factor, etc. between Python and MT5
- **Debug discrepancies**: Any differences are due to MT5 tick model / order fill, not strategy params

### Running Strategy Tester in Parity Mode

1. **Attach EA** to Strategy Tester
2. **Set Parameters:**
   ```
   BacktestParityMode = true  (force best backtest params)
   SymbolToCheck = EURUSD
   Timeframe = H1
   LookbackBars = 400
   EnableTrading = true
   ```
3. **Check Experts Tab** - Should see:
   ```
   *** BACKTEST PARITY MODE ACTIVE ***
   Forcing best backtest parameters (overriding inputs):
     MinConfidence: 0.60
     BrokenLevelCooldownHours: 48.0
     BrokenLevelBreakPips: 15.0
     MinEdgePips: 4.0
   Cost Model:
     SpreadPips: 1.0
     SlippagePips: 0.5
     CommissionPerSidePerLot: $7.0
     UsdPerPipPerLot: $10.0
     LotSize: 1.0
   ```
4. **Run backtest** - Results should closely match Python backtest (within tick model differences)

## Step 1: Deploy EA to MT5 (SIMPLIFIED - No DLL Needed!)

### Copy Expert Advisor

1. **Find MT5 Data Folder:**
   - In MT5: File → Open Data Folder
   - Typical path: `C:\Users\[User]\AppData\Roaming\MetaQuotes\Terminal\[ID]\`

2. **Copy EA:**
   ```
   Copy: mt5_integration/volarix4.mq5
   To:   [MT5 Data Folder]\MQL5\Experts\volarix4.mq5
   ```

## Step 2: Configure MT5

### Enable WebRequest

1. Tools → Options → Expert Advisors
2. Check ✅ **Allow WebRequest for listed URL**
3. Add URL: `http://localhost:8000`
4. Click OK

### Compile EA

1. MetaEditor → Open `volarix4.mq5`
2. Compile (F7)
3. Check for errors
4. Should compile successfully without DLL dependency

## Step 4: Run the EA

### Start Volarix 4 API

```bash
cd E:\prs\frx_news_root\volarix4
python -m volarix4.run
```

Verify API is running:
- Open browser: `http://localhost:8000/docs`
- Should see Swagger UI

### Attach EA to Chart

1. **Open Chart**
   - File → New Chart → EURUSD (or your symbol)
   - Set timeframe: H1

2. **Attach EA**
   - Navigator (Ctrl+N) → Expert Advisors → volarix4
   - Drag onto chart

3. **Configure Parameters**
   ```
   # Basic Settings
   SymbolToCheck: EURUSD
   Timeframe: H1
   LookbackBars: 400
   API_URL: http://localhost:8000

   # Trade Management
   RiskPercent: 1.0
   MaxPositions: 1
   EnableTrading: true (for live), false (for testing)

   # Backtest Parity Mode (RECOMMENDED)
   BacktestParityMode: true

   # Strategy Parameters (only used if BacktestParityMode = false)
   MinConfidence: 0.60
   BrokenLevelCooldownHours: 48.0
   BrokenLevelBreakPips: 15.0
   MinEdgePips: 4.0

   # Cost Model (only used if BacktestParityMode = false)
   SpreadPips: 1.0
   SlippagePips: 0.5
   CommissionPerSidePerLot: 7.0
   UsdPerPipPerLot: 10.0
   LotSize: 1.0
   ```

4. **Enable AutoTrading**
   - Click "AutoTrading" button (or F4)
   - EA should show 😊 (happy face) in top-right corner

## Verification

### Check EA is Running

**MT5 Experts Tab** (Toolbox → Experts):
```
=================================================
Volarix 4 EA Started - S/R Bounce Strategy
=================================================
Symbol: EURUSD
Timeframe: H1
Lookback Bars: 400
API URL: http://localhost:8000
Auto-Trading: ENABLED
Backtest Parity Mode: ENABLED
=================================================
*** BACKTEST PARITY MODE ACTIVE ***
Forcing best backtest parameters (overriding inputs):
  MinConfidence: 0.60
  BrokenLevelCooldownHours: 48.0
  BrokenLevelBreakPips: 15.0
  MinEdgePips: 4.0
Cost Model:
  SpreadPips: 1.0
  SlippagePips: 0.5
  CommissionPerSidePerLot: $7.0
  UsdPerPipPerLot: $10.0
  LotSize: 1.0
=================================================
Make sure 'Allow Web Requests' is enabled for:
  http://localhost:8000
=================================================
```

### Check API Calls

**API Log** (in terminal running the API):
```
[INFO] >> POST /signal
[INFO] ======================================================================
[INFO] RESOLVED STRATEGY PARAMETERS (Backtest Parity Mode)
[INFO] ======================================================================
[INFO]   min_confidence: 0.6
[INFO]   broken_level_cooldown_hours: 48.0
[INFO]   broken_level_break_pips: 15.0
[INFO]   min_edge_pips: 4.0
[INFO] Cost Model Parameters:
[INFO]   spread_pips: 1.0
[INFO]   slippage_pips: 0.5
[INFO]   commission_per_side_per_lot: $7.0
[INFO]   usd_per_pip_per_lot: $10.0
[INFO]   lot_size: 1.0
[INFO] ======================================================================
[INFO] Signal request: EURUSD [Single-TF]
[INFO] [DEBUG] Total bars received: 400
[INFO] [DEBUG] Bars with time=0: 0 out of 400  ← SHOULD BE 0!
[INFO] [DEBUG] First timestamp: 2024-01-22 02:00:00  ← CORRECT YEAR!
[INFO] S/R Levels Detected: 3
[INFO] Checking Broken Level Filter...
[INFO] Broken Level Filter: PASSED
[INFO] Rejection Found: SELL at 1.04368
[INFO] Confidence Filter: PASSED (0.65 >= 0.60)
[INFO] Checking Minimum Edge After Costs...
[INFO] Edge Filter: PASSED - Sufficient edge after costs
[INFO] Trade Setup Calculated: Entry=1.04277, SL=1.04468, TP=1.03895
```

### Check Trade Execution

**MT5 Experts Tab:**
```
API Response: Signal=SELL, Confidence=0.62, Entry=1.04277, SL=1.04468, TP=1.03895
Opening trade: SELL at 1.04277, SL=1.04468, TP=1.03895, Lot=0.01
Trade opened: Ticket=12345, Price=1.04277, SL=1.04468, TP=1.03895, Lot=0.01
```

## Troubleshooting

### Corrupted Data (Wrong Dates: 1970, 1963, 2003)

**Symptom:**
```
[INFO] Session Check: INVALID (1970-01-01 00:00:00)
[INFO] [DEBUG] Bar [1]: time=0, open=0.00000, close=0.00000
[INFO] [DEBUG] Bar [2]: time=644588692, close=618223114235821496766...
```

**Cause:** Struct alignment mismatch

**Fix:**
1. Verify `#pragma pack(push, 1)` in volarix4_bridge.cpp:24
2. Verify `long long timestamp` (not `long`)
3. Rebuild DLL completely (clean + rebuild)
4. Restart MT5 to unload old DLL
5. Check debug log shows "44 bytes"

### No TP/SL Set on Trades

**Symptom:**
```
Trade opened: Ticket=12345, Price=1.04277, SL=0.00000, TP=0.00000
```

**Cause:** MQ5 not parsing API response

**Fix:**
1. Check volarix4.mq5 lines 288-307 (JSON parsing)
2. Ensure `request.tp = tp2;` on line 351
3. Verify API returns non-zero TP values
4. Recompile volarix4.mq5

### DLL Not Loading

**Symptom:**
```
ERROR: DLL call failed with error code 127
Cannot load DLL 'Volarix4Bridge.dll'
```

**Fix:**
1. Check DLL is in `MQL5\Libraries\Volarix4Bridge.dll`
2. Enable "Allow DLL imports" in MT5 Options
3. Compile DLL for x64 (not x86)
4. Check missing dependencies (Visual C++ Redistributable)

### Non-Deterministic Trades

**Symptom:**
- Same backtest gives different trades each run
- Random S/R levels detected
- Different signals on same bar

**Cause:** Memory corruption from struct mismatch

**Fix:**
1. Same as "Corrupted Data" above
2. Verify struct size = 44 bytes exactly
3. No random padding bytes

### API Not Responding

**Symptom:**
```
WARNING: Empty response from API
```

**Cause:** API not running or wrong port

**Fix:**
1. Start API: `python -m volarix4.run`
2. Check API running: `http://localhost:8000/docs`
3. Check port 8000 not blocked
4. Verify DLL connects to `localhost:8000` (volarix4_bridge.cpp:116)

## Configuration

### Change API Port

**In volarix4_bridge.cpp (line 116):**
```cpp
HINTERNET hConnect = InternetConnectA(hInternet,
    "localhost",  // Change to your API server IP
    8000,         // Change to your API port
    NULL, NULL, INTERNET_SERVICE_HTTP, 0, 0);
```

Then rebuild DLL.

### Adjust Strategy Parameters

**In volarix4.mq5 (lines 39-47):**
```mql5
input string SymbolToCheck = "EURUSD";
input ENUM_TIMEFRAMES Timeframe = PERIOD_H1;
input int    LookbackBars  = 400;         // More bars = slower but more data
input double RiskPercent = 1.0;           // Risk per trade (%)
input int    MaxPositions = 1;
input bool   EnableTrading = true;
```

### Adjust S/R Detection

**In API config.py:**
```python
SR_CONFIG = {
    "min_level_score": 60.0,  # Lower = more signals
    "cluster_pips": 10.0,     # Tighter clustering
}

REJECTION_CONFIG = {
    "min_wick_body_ratio": 1.5,  # Lower = more signals
    "lookback_candles": 5,        # Check more recent candles
}
```

## Performance Optimization

### Reduce API Calls

- EA calls API only on new bars (not every tick)
- Uses `IsNewBar()` function to detect bar changes
- Typical: 1 call per hour on H1 timeframe

### Debug Logging

**Disable in production:**

Remove debug logging from volarix4_bridge.cpp lines 59-74 for faster execution:
```cpp
// Comment out or remove in production:
// WriteDebugLog(struct_debug.str().c_str());
```

### Multiple Symbols

Run one EA instance per symbol:
- Each EA has separate state
- No interference between symbols
- Can run different parameters per symbol

## Best Practices

### Testing

1. **Backtest First**
   - Enable Trading: false
   - Run in Strategy Tester
   - Verify correct dates (2024, not 1970)
   - Check SL/TP are set

2. **Demo Account**
   - Enable Trading: true
   - Test on demo for 1 week
   - Monitor logs daily

3. **Live Trading**
   - Start with minimum risk (0.5%)
   - Monitor first 10 trades closely
   - Gradually increase risk if performing well

### Monitoring

- Check MT5 Experts tab for errors
- Check API logs: `logs/volarix4_YYYY-MM-DD.log`
- Review trade log: `[MT5 Data]\Files\volarix4_log.csv`
- Monitor parameter logging on each new bar

### Updates

**After updating EA:**
1. Recompile in MetaEditor
2. Remove EA from chart
3. Reattach EA to chart
4. Verify BacktestParityMode parameters in Experts tab

## Expected Differences: Python Backtest vs MT5

Even with Backtest Parity Mode enabled, you may see small differences between `tests/backtest.py` and MT5 Strategy Tester results:

### 1. **Tick Model Differences**

**Python Backtest:**
- Uses OHLC bar data only
- Entry filled at exact rejection entry price
- TP/SL hit at exact levels

**MT5 Strategy Tester:**
- Generates ticks based on tick model ("Every tick", "OHLC", "1 minute OHLC", etc.)
- Entry may be filled at Ask/Bid with spread
- TP/SL may be hit earlier/later due to synthetic tick generation
- Slippage simulation may vary

**Impact:**
- Win rate may differ by ±2-5%
- Individual trade P&L may vary slightly
- Overall profit factor should be similar (within 10-15%)

### 2. **Order Fill Rules**

**Python Backtest:**
- Instant fill at calculated price
- No spread/slippage unless explicitly modeled (which we now do)
- No requotes or partial fills

**MT5 Strategy Tester:**
- Simulates broker execution
- Spread applied on entry (buy at Ask, sell at Bid)
- May model requotes, partial fills depending on settings
- Commission applied per broker settings

**Impact:**
- MT5 will show slightly higher transaction costs
- Entry prices may differ by spread amount
- Some signals may not fill if price doesn't reach entry

### 3. **Timestamp Precision**

**Python Backtest:**
- Uses bar close time
- Signal generated at bar close

**MT5 Strategy Tester:**
- Uses bar open time for next bar (EA runs on new bar)
- Slight timing offset (seconds to minutes)

**Impact:**
- Minimal - both use same OHLC data
- May affect session filter edge cases

### 4. **Cost Model Precision**

**Python Backtest:**
- Calculates exact costs per trade
- `total_cost_pips = spread + 2*slippage + commission_pips`
- Filters based on exact min_edge

**MT5 Strategy Tester:**
- Uses broker's commission settings
- Spread may vary per tick
- Slippage applied at execution (not deterministic)

**Impact:**
- Edge filter may behave slightly differently
- Some borderline trades may be filtered in Python but not MT5 (or vice versa)

### 5. **What Should Match Closely**

✅ **These should be nearly identical:**
- Number of signals generated (±5%)
- Signal direction (BUY/SELL) on same bars
- Confidence scores
- Entry/SL/TP levels (within spread tolerance)
- Filter rejection reasons (confidence, broken level, edge)

❌ **These will differ:**
- Exact fill prices (spread/slippage)
- Exact profit in USD (execution differences)
- Time of signal (seconds offset)

### Recommended Comparison

To compare Python backtest with MT5:

1. **Run Python backtest:**
   ```bash
   python tests/backtest.py --min_confidence 0.60 --broken_level_cooldown_hours 48.0 --min_edge_pips 4.0
   ```

2. **Run MT5 Strategy Tester:**
   - BacktestParityMode = true
   - Same date range
   - Same symbol (EURUSD)
   - Tick model: "Every tick" or "1 minute OHLC"
   - Spread: Fixed at 1.0 pip (or whatever Python uses)

3. **Compare metrics:**
   - Total signals generated: Should be within 5%
   - Win rate: Should be within 3-5%
   - Avg win/loss: Should be similar
   - Profit factor: Should be within 10-15%

4. **Investigate large discrepancies:**
   - Check API logs for filtered signals
   - Verify parameters are being applied
   - Check MT5 spread settings match Python
   - Review individual trades where results differ

## Debug Checklist

When things aren't working:

- [ ] API is running (`http://localhost:8000/docs` loads)
- [ ] "Allow WebRequest for listed URL" is enabled in MT5
- [ ] URL `http://localhost:8000` is in allowed list
- [ ] BacktestParityMode = true (or custom params set correctly)
- [ ] API log shows "RESOLVED STRATEGY PARAMETERS"
- [ ] API log shows correct parameter values (0.60, 48.0, etc.)
- [ ] Timestamps are correct year (2024+, not 1970)
- [ ] EA shows parameters correctly on attach
- [ ] AutoTrading is enabled (😊 face)
- [ ] MT5 Experts tab shows no errors

## Support

If you encounter issues not covered here:

1. Check `E:\Volarix4Bridge_Debug.txt`
2. Check `logs/volarix4_YYYY-MM-DD.log`
3. Enable debug logging in API (see main.py lines 232-249)
4. Run test: `python test_api.py`
5. Post issue with logs to GitHub

## Summary

**Minimum Viable Setup (SIMPLIFIED - No DLL!):**
1. Copy `mt5_integration/volarix4.mq5` to `MQL5\Experts\`
2. Enable WebRequest in MT5 for `http://localhost:8000`
3. Compile EA in MetaEditor
4. Start API: `python -m volarix4.run`
5. Attach EA to chart with `BacktestParityMode = true`
6. Verify parameters in Experts tab
7. Enable AutoTrading

**Success Indicators:**
- ✅ API log shows "RESOLVED STRATEGY PARAMETERS"
- ✅ Parameters match backtest: 0.60, 48.0h, 4.0 pips
- ✅ Bars with time=0: 0 out of 400
- ✅ Correct dates (2024+)
- ✅ SL and TP set on trades
- ✅ Edge filter passes/fails match Python backtest logic

**Backtest Parity:**
- MT5 Strategy Tester results should be comparable to `tests/backtest.py`
- Same signals generated (±5%)
- Same filter logic (confidence, broken levels, edge)
- Expected differences are tick model and order fill rules only

Your MT5 integration with backtest parity is now complete! 🚀
