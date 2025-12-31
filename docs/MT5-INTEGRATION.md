# MT5 Integration Guide - Volarix 4

Complete guide for integrating Volarix 4 API with MetaTrader 5 using the **DLL bridge** with **backtest parity** support.

## Overview

The MT5 integration uses a **C++ DLL bridge** to call the API with full strategy parameters matching `tests/backtest.py`:
1. **Volarix4Bridge.dll** - C++ bridge that handles HTTP communication with the API
2. **volarix4.mq5** - Expert Advisor that uses the DLL to get signals and executes trades
3. **Backtest Parity Mode** - Forces best backtest parameters for comparable results

## Architecture

```
MT5 Chart / Strategy Tester
    ↓
volarix4.mq5 (Expert Advisor)
    ↓ DLL Call
Volarix4Bridge.dll (C++ Bridge)
    ↓ HTTP POST (with strategy parameters)
Volarix 4 API (FastAPI)
    ↓ (applies same filters as tests/backtest.py)
Response (Signal + SL/TP)
    ↓ DLL Return
volarix4.mq5 executes trade
```

## Prerequisites

- **MetaTrader 5** (64-bit)
- **Visual Studio** (2019 or later, for DLL compilation)
- **Volarix 4 API** running on `localhost:8000`
- **Windows** (DLL is platform-specific)

## Step 1: Compile the DLL Bridge

### Using Visual Studio

1. **Open Visual Studio** → Create New Project → "Dynamic-Link Library (DLL)"

2. **Add Source File:**
   - Copy `mt5_integration/volarix4_bridge.cpp` into project

3. **Project Settings:**
   - Platform: **x64** (not x86 - must match MT5 64-bit)
   - Configuration: **Release** (for production)
   - C/C++ → Precompiled Headers → "Not Using Precompiled Headers"

4. **Build:**
   - Build → Build Solution
   - Output: `x64\Release\Volarix4Bridge.dll`

5. **Deploy DLL:**
   ```
   Copy: x64\Release\Volarix4Bridge.dll
   To:   [MT5 Data Folder]\MQL5\Libraries\Volarix4Bridge.dll
   ```

**To find MT5 Data Folder:**
- In MT5: File → Open Data Folder
- Typical path: `C:\Users\[User]\AppData\Roaming\MetaQuotes\Terminal\[ID]\`

### Using Command Line (MinGW)

```bash
g++ -shared -o Volarix4Bridge.dll volarix4_bridge.cpp -lwininet -lole32 -loleaut32
copy Volarix4Bridge.dll "C:\Users\[User]\AppData\Roaming\MetaQuotes\Terminal\[ID]\MQL5\Libraries\"
```

### Verify DLL Structure

The DLL debug log will show:
```
OHLCVBar struct size: 44 bytes (should be 44)
```

**If not 44 bytes:**
- Check `#pragma pack(1)` is present
- Verify `long long timestamp` (not `long`)
- Clean and rebuild

## Step 2: Deploy EA to MT5

### Important: Closed Bars Only (Parity Contract)

**CRITICAL:** The EA sends **ONLY closed bars** to the API, matching the Parity Contract:
- Uses `CopyRates(symbol, timeframe, 1, count)` - starts from index 1 (last closed bar)
- Skips index 0 (current forming bar) to ensure deterministic results
- This matches `tests/backtest.py` behavior exactly

**Why this matters:**
- Backtest uses only closed bars → MT5 must match
- Forming bars have unreliable OHLC (only 1 tick at bar open)
- Ensures API receives same bar state whether called live or in backtest

### Copy Expert Advisor

```
Copy: mt5_integration/volarix4.mq5
To:   [MT5 Data Folder]\MQL5\Experts\volarix4.mq5
```

### Compile EA

1. **Open MetaEditor** (F4 in MT5)
2. **Open** `volarix4.mq5`
3. **Compile** (F7)
4. **Check for errors** - should compile successfully

## Step 3: Configure MT5

### Enable DLL Imports

1. **Tools** → **Options** → **Expert Advisors**
2. **Check** ✅ **Allow DLL imports**
3. **Check** ✅ **Allow WebRequest for listed URL** (for DLL's HTTP calls)
4. **Add URL:** `http://localhost:8000`
5. **Click OK**

**IMPORTANT:** Both options must be enabled:
- "Allow DLL imports" - so EA can load Volarix4Bridge.dll
- "Allow WebRequest" - so DLL can make HTTP calls to API

## Step 4: Run the EA

### Start Volarix 4 API

```bash
cd E:\prs\frx_news_root\volarix4
python run.py
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
   EnableTrading: false (for testing), true (for live)

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

## Backtest Parity Mode

**NEW:** The EA supports **Backtest Parity Mode** to make MT5 Strategy Tester results comparable to `tests/backtest.py`.

### How It Works

When `BacktestParityMode = true` (default), the EA:
1. **Forces** best backtest parameters regardless of input values:
   - `min_confidence = 0.60`
   - `broken_level_cooldown_hours = 48.0`
   - `broken_level_break_pips = 15.0`
   - `min_edge_pips = 4.0`
   - Standard cost model: spread=1.0, slippage=0.5, commission=$7/lot
2. **Logs** all active parameters to MT5 Experts tab on startup
3. **Sends** these parameters to the API via DLL in every request
4. **Ensures** API applies same filters as Python backtest

### Why Use Backtest Parity Mode?

- **Comparable results**: MT5 Strategy Tester uses same strategy logic as `tests/backtest.py`
- **Apples-to-apples**: Compare win rate, profit factor, etc. between Python and MT5
- **Debug discrepancies**: Any differences are due to MT5 tick model / order fill, not strategy params

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
Make sure 'Allow DLL imports' is enabled
Volarix4Bridge.dll must be in MQL5\Libraries\
=================================================
```

**On Each New Bar:**
```
New H1 candle at 2025.02.10 16:00 - Calling Volarix 4 API...
Calling DLL: GetVolarix4Signal()
  Symbol: EURUSD
  Timeframe: H1
  Bars to send: 400
  Min Confidence: 0.60
  Min Edge (pips): 4.0
```

**Critical indicators:**
- ✅ DLL call succeeds (no error code)
- ✅ Response received from API
- ✅ Parameters sent correctly

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
[INFO] Bar count: 400
[INFO] First bar time: 2024-12-25 12:00:00 (timestamp: 1735128000)
[INFO] Last bar time: 2025-02-10 15:00:00 (timestamp: 1739185200)
[INFO] Validation: PASSED
[INFO] ======================================================================
```

**Check DLL Debug Log:**
```
File: E:\Volarix4Bridge_Debug.txt

=== DLL Called ===
OHLCVBar struct size: 44 bytes (should be 44)
Bar count: 400
First bar: timestamp=1735128000, open=1.08495, close=1.08537
=== Volarix 4 API Call ===
Symbol: EURUSD
Timeframe: H1
Bars: 400
API Response (285 bytes): {"signal":"BUY","confidence":0.75,...
```

### Check Trade Execution

**MT5 Experts Tab:**
```
API Response: Signal=SELL, Confidence=0.62, Entry=1.04277, SL=1.04468, TP=1.03895
Opening trade: SELL at 1.04277, SL=1.04468, TP=1.03895, Lot=0.01
Trade opened: Ticket=12345, Price=1.04277, SL=1.04468, TP=1.03895, Lot=0.01
```

## Troubleshooting

### DLL Not Loading

**Symptom:**
```
ERROR: DLL call failed with error code 127
Cannot load DLL 'Volarix4Bridge.dll'
```

**Fix:**
1. **Check DLL location:** `[MT5 Data Folder]\MQL5\Libraries\Volarix4Bridge.dll`
2. **Enable DLL imports:** Tools → Options → Expert Advisors → ✅ "Allow DLL imports"
3. **Check architecture:** DLL must be x64 (not x86) to match MT5 64-bit
4. **Install Visual C++ Redistributable:** Download from Microsoft if missing
5. **Check Windows didn't block DLL:** Right-click DLL → Properties → Unblock (if present)

### Corrupted Data (Wrong Dates: 1970, 1963, 2003)

**Symptom:**
```
[INFO] [DEBUG] Bar [1]: time=0, open=0.00000, close=0.00000
[INFO] [DEBUG] First timestamp: 1970-01-01 00:00:00
```

**Cause:** Struct alignment mismatch between MQL5 and C++

**Fix:**
1. **Verify `#pragma pack(1)` in volarix4_bridge.cpp:24**
2. **Verify `long long timestamp` (not `long`)** in volarix4_bridge.cpp:27
3. **Rebuild DLL completely** (clean + rebuild)
4. **Restart MT5** to unload old DLL from memory
5. **Check debug log shows "44 bytes"** in E:\Volarix4Bridge_Debug.txt

### Weekend Gap Validation Errors

**Symptom:**
```
[ERROR] Bar validation failed: Excessive gap at index 58: gap of 49 periods
```

**Cause:** Weekend market closure creates ~49-hour gaps in H1 data

**Fix:**
- **Already fixed in current version** - API now accepts gaps up to 168 periods (1 week)
- If still seeing errors, restart API server to load updated `bar_validation.py`

### No TP/SL Set on Trades

**Symptom:**
```
Trade opened: Ticket=12345, Price=1.04277, SL=0.00000, TP=0.00000
```

**Cause:** MQ5 not parsing API response correctly

**Fix:**
1. Check API response includes `"sl"` and `"tp2"` fields
2. Verify JSON parsing in volarix4.mq5 (lines 330-342)
3. Ensure `request.sl = sl;` and `request.tp = tp2;` are set
4. Recompile volarix4.mq5

### API Not Responding

**Symptom:**
```
WARNING: Empty response from API
```

**Cause:** API not running or wrong port

**Fix:**
1. **Start API:** `python run.py`
2. **Check API running:** `http://localhost:8000/docs`
3. **Check firewall:** Port 8000 not blocked
4. **Check API_URL parameter in EA:** Must match DLL configuration

### API Returns Error 422

**Symptom:**
```
API Response (422 bytes): {"detail":"Bar validation failed: ..."}
```

**Cause:** Bar validation failed (see specific error message)

**Common Issues:**
- **Weekend gaps:** Already fixed, restart API server
- **Insufficient bars:** Need at least 200 bars, increase LookbackBars parameter
- **Time == 0:** Data corruption, see "Corrupted Data" section above

## Configuration

### Change API Port

**In volarix4.mq5 (line 44):**
```mql5
input string API_URL = "http://localhost:8000";  // Change port here
```

**In volarix4_bridge.cpp (dynamic parsing):**
- No change needed - DLL automatically parses host:port from API_URL
- Rebuild EA and reattach to chart

### Adjust Strategy Parameters

**Disable Backtest Parity Mode:**
```mql5
input bool BacktestParityMode = false;  // Use custom parameters
```

**Then customize:**
```mql5
input double MinConfidence = 0.70;               // Higher = fewer signals
input double BrokenLevelCooldownHours = 72.0;    // Longer cooldown
input double MinEdgePips = 6.0;                  // Require more edge
```

## Best Practices

### Testing Workflow

1. **Backtest First** (Strategy Tester)
   - EnableTrading: false
   - BacktestParityMode: true
   - Verify correct dates (2024+, not 1970)
   - Check SL/TP are set
   - Compare results with `tests/backtest.py`

2. **Demo Account** (Forward Test)
   - EnableTrading: true
   - Test on demo for 1 week
   - Monitor logs daily
   - Verify parity with backtest behavior

3. **Live Trading**
   - Start with minimum risk (0.5%)
   - Monitor first 10 trades closely
   - Gradually increase risk if performing well

### Monitoring

- **MT5 Experts tab** for errors and trade execution
- **API logs:** `logs/volarix4_YYYY-MM-DD.log`
- **DLL debug log:** `E:\Volarix4Bridge_Debug.txt`
- **Trade log:** `[MT5 Data]\Files\volarix4_log.csv`

### Updates

**After updating volarix4_bridge.cpp:**
1. Rebuild DLL
2. Copy new DLL to `MQL5\Libraries\`
3. Restart MT5 to unload old DLL
4. Reattach EA to chart

**After updating volarix4.mq5:**
1. Recompile in MetaEditor
2. Remove EA from chart
3. Reattach EA to chart
4. Verify parameters in Experts tab

**After updating API:**
1. Restart API server: `python run.py`
2. No EA changes needed

## Expected Differences: Python Backtest vs MT5

Even with Backtest Parity Mode enabled, you may see small differences:

### What Should Match

✅ **These should be nearly identical:**
- Number of signals generated (±5%)
- Signal direction (BUY/SELL) on same bars
- Confidence scores
- Entry/SL/TP levels (within spread tolerance)
- Filter rejection reasons

### What Will Differ

❌ **These will differ:**
- Exact fill prices (spread/slippage)
- Exact profit in USD (execution differences)
- Time of signal (seconds offset)
- Tick model effects on TP/SL hits

**Impact:**
- Win rate may differ by ±2-5%
- Overall profit factor should be similar (within 10-15%)

## Debug Checklist

When things aren't working:

- [ ] API is running (`http://localhost:8000/docs` loads)
- [ ] "Allow DLL imports" is enabled in MT5
- [ ] "Allow WebRequest for listed URL" is enabled in MT5
- [ ] URL `http://localhost:8000` is in allowed list
- [ ] Volarix4Bridge.dll exists in `MQL5\Libraries\`
- [ ] DLL is x64 architecture
- [ ] BacktestParityMode = true (or custom params set correctly)
- [ ] API log shows "RESOLVED STRATEGY PARAMETERS"
- [ ] DLL debug log shows "44 bytes"
- [ ] Timestamps are correct year (2024+, not 1970)
- [ ] EA shows parameters correctly on attach
- [ ] AutoTrading is enabled (😊 face)
- [ ] MT5 Experts tab shows no errors

## Summary

**Setup Steps:**
1. ✅ Compile `volarix4_bridge.cpp` to `Volarix4Bridge.dll` (x64 Release)
2. ✅ Copy DLL to `[MT5 Data Folder]\MQL5\Libraries\`
3. ✅ Copy `volarix4.mq5` to `[MT5 Data Folder]\MQL5\Experts\`
4. ✅ Enable "Allow DLL imports" in MT5
5. ✅ Enable "Allow WebRequest" for `http://localhost:8000` in MT5
6. ✅ Compile EA in MetaEditor
7. ✅ Start API: `python run.py`
8. ✅ Attach EA to chart with `BacktestParityMode = true`
9. ✅ Enable AutoTrading

**Success Indicators:**
- ✅ DLL debug log shows "44 bytes"
- ✅ API log shows "RESOLVED STRATEGY PARAMETERS"
- ✅ Parameters match backtest: 0.60, 48.0h, 4.0 pips
- ✅ Bar validation passes (168-period gap tolerance)
- ✅ Correct dates (2024+)
- ✅ SL and TP set on trades
- ✅ Results comparable to `tests/backtest.py`

Your MT5 integration with DLL bridge and backtest parity is now complete! 🚀
