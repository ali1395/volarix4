# MT5 Integration Guide - Volarix 4

Complete guide for integrating Volarix 4 API with MetaTrader 5 using the C++ DLL bridge.

## Overview

The MT5 integration consists of two components:
1. **Volarix4Bridge.dll** - C++ bridge that sends OHLCV data to the API
2. **volarix4.mq5** - Expert Advisor that calls the DLL and executes trades

## Architecture

```
MT5 Chart
    ↓
volarix4.mq5 (Expert Advisor)
    ↓
Volarix4Bridge.dll (C++ Bridge)
    ↓ HTTP POST
Volarix 4 API (FastAPI)
    ↓
Response (Signal + SL/TP)
    ↓
volarix4.mq5 executes trade
```

## Prerequisites

- Visual Studio 2019+ (for compiling DLL)
- MetaTrader 5 (64-bit)
- Volarix 4 API running on `localhost:8000`

## Step 1: Compile the DLL

### Critical Struct Alignment Fix

⚠️ **IMPORTANT**: The struct definition MUST use `#pragma pack(1)` and `long long timestamp` to match MQL5's memory layout exactly.

**Correct struct (volarix4_bridge.cpp:24-34):**
```cpp
#pragma pack(push, 1)  // No padding!
struct OHLCVBar
{
    long long timestamp; // 8 bytes (NOT long!)
    double open;         // 8 bytes
    double high;         // 8 bytes
    double low;          // 8 bytes
    double close;        // 8 bytes
    int volume;          // 4 bytes
};                       // Total: exactly 44 bytes
#pragma pack(pop)
```

**Why This Matters:**
- Without `#pragma pack(1)`: Struct = 48 bytes (compiler adds padding)
- With `#pragma pack(1)`: Struct = 44 bytes (matches MQL5)
- Wrong packing = corrupted data, wrong dates, garbage prices

### Compilation Steps

1. **Open Visual Studio Project**
   - Create new C++ DLL project or use existing
   - Add `volarix4_bridge.cpp`
   - Set configuration to **Release | x64**

2. **Build Settings**
   ```
   Platform: x64 (NOT x86!)
   Configuration: Release
   Runtime Library: Multi-threaded DLL (/MD)
   ```

3. **Build the DLL**
   - Build → Build Solution (Ctrl+Shift+B)
   - Output: `Volarix4Bridge.dll`

4. **Verify Struct Size**
   - Check debug log after first call: `E:\Volarix4Bridge_Debug.txt`
   - Should see: `OHLCVBar struct size: 44 bytes (should be 44)`
   - If it says 48 bytes, the packing didn't work!

## Step 2: Deploy to MT5

### Copy DLL to MT5

1. **Find MT5 Data Folder:**
   - In MT5: File → Open Data Folder
   - Typical path: `C:\Users\[User]\AppData\Roaming\MetaQuotes\Terminal\[ID]\`

2. **Copy DLL:**
   ```
   Copy: Volarix4Bridge.dll
   To:   [MT5 Data Folder]\MQL5\Libraries\Volarix4Bridge.dll
   ```

3. **Verify Copy:**
   ```cmd
   dir "%APPDATA%\MetaQuotes\Terminal\*\MQL5\Libraries\Volarix4Bridge.dll"
   ```

### Copy Expert Advisor

```
Copy: volarix4.mq5
To:   [MT5 Data Folder]\MQL5\Experts\volarix4.mq5
```

## Step 3: Configure MT5

### Enable DLL Imports

1. Tools → Options → Expert Advisors
2. Check ✅ **Allow DLL imports**
3. Check ✅ **Allow WebRequest for listed URL**
4. Add URL: `http://localhost:8000`
5. Click OK

### Recompile EA (if modified)

If you modified volarix4.mq5:
1. MetaEditor → Open `volarix4.mq5`
2. Compile (F7)
3. Check for errors
4. Verify it shows: `#import "Volarix4Bridge.dll"`

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
   Symbol: EURUSD
   Timeframe: H1
   Lookback Bars: 50
   Risk Percent: 1.0
   Max Positions: 1
   Enable Trading: true (for live), false (for testing)
   ```

4. **Enable AutoTrading**
   - Click "AutoTrading" button (or F4)
   - EA should show 😊 (happy face) in top-right corner

## Verification

### Check EA is Running

**MT5 Experts Tab** (Toolbox → Experts):
```
Volarix 4 EA Started - S/R Bounce Strategy
Symbol: EURUSD
Timeframe: H1
Lookback Bars: 50
API URL: http://localhost:8000
Auto-Trading: ENABLED
```

### Check DLL Calls

**DLL Debug Log** (`E:\Volarix4Bridge_Debug.txt`):
```
=== DLL Called ===
OHLCVBar struct size: 44 bytes (should be 44)  ← MUST BE 44!
Bar count: 50
First bar: timestamp=1705888800, open=1.08921, close=1.09012
Second bar: timestamp=1705892400, open=1.09014, close=1.09020  ← NOT ZEROS!
```

### Check API Calls

**API Log** (in terminal running the API):
```
[INFO] >> POST /signal
[INFO] Signal request: EURUSD [Single-TF]
[INFO] [DEBUG] Bars with time=0: 0 out of 50  ← SHOULD BE 0!
[INFO] [DEBUG] First timestamp: 2024-01-22 02:00:00  ← CORRECT YEAR!
[INFO] S/R Levels Detected: 3
[INFO] Rejection Found: SELL at 1.04368
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
input int    LookbackBars  = 50;          // More bars = slower but more data
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

- Check DLL debug log daily: `E:\Volarix4Bridge_Debug.txt`
- Check MT5 Experts tab for errors
- Check API logs: `logs/volarix4_YYYY-MM-DD.log`
- Review trade log: `[MT5 Data]\Files\volarix4_log.csv`

### Updates

**After updating DLL:**
1. Rebuild DLL
2. Copy to MT5 Libraries folder
3. **Restart MT5** (critical!)
4. Reattach EA to chart

**After updating MQ5:**
1. Recompile in MetaEditor
2. Remove EA from chart
3. Reattach EA to chart

## Debug Checklist

When things aren't working:

- [ ] API is running (`http://localhost:8000/docs` loads)
- [ ] DLL is in `MQL5\Libraries\Volarix4Bridge.dll`
- [ ] "Allow DLL imports" is enabled in MT5
- [ ] DLL compiled for x64 (not x86)
- [ ] DLL debug log shows struct size = 44 bytes
- [ ] API log shows "Bars with time=0: 0 out of 50"
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

**Minimum Viable Setup:**
1. Compile `volarix4_bridge.cpp` → `Volarix4Bridge.dll` (x64, pack=1)
2. Copy DLL to `MQL5\Libraries\`
3. Copy `volarix4.mq5` to `MQL5\Experts\`
4. Enable DLL imports in MT5
5. Start API: `python -m volarix4.run`
6. Attach EA to chart
7. Verify struct size = 44 bytes
8. Verify no zero timestamps
9. Enable AutoTrading

**Success Indicators:**
- ✅ Struct size: 44 bytes
- ✅ Bars with time=0: 0 out of 50
- ✅ Correct dates (2024+)
- ✅ SL and TP set on trades
- ✅ Deterministic backtest results

Your MT5 integration is now complete! 🚀
