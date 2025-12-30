# Volarix 4 - MT5 Integration

Integration files for connecting MetaTrader 5 to Volarix 4 API.

## Files

- **volarix4.mq5** - MT5 Expert Advisor (EA)
- **volarix4_bridge.cpp** - C++ DLL bridge (connects EA to API)
- **volarix3/** - Legacy Volarix 3 files (multi-TF, ML models)

## Quick Start

### 1. Compile the C++ DLL

**Using Visual Studio:**

1. Open Visual Studio → Create New Project → "Dynamic-Link Library (DLL)"
2. Add `volarix4_bridge.cpp` to the project
3. Project Properties → C/C++ → Precompiled Headers → Set to "Not Using"
4. Build → Build Solution (x64 Release)
5. Copy `Volarix4Bridge.dll` to `C:\Program Files\MetaTrader 5\MQL5\Libraries\`

**Using Command Line (MinGW):**

```bash
g++ -shared -o Volarix4Bridge.dll volarix4_bridge.cpp -lwininet -lole32 -loleaut32
copy Volarix4Bridge.dll "C:\Program Files\MetaTrader 5\MQL5\Libraries\"
```

### 2. Install the MT5 Expert Advisor

1. Copy `volarix4.mq5` to `C:\Users\YourName\AppData\Roaming\MetaQuotes\Terminal\<ID>\MQL5\Experts\`
2. Open MetaEditor → Compile `volarix4.mq5`
3. Restart MT5

### 3. Configure MT5 Settings

**IMPORTANT:** Enable DLL imports

1. MT5 → Tools → Options → Expert Advisors
2. Check ✅ "Allow DLL imports"
3. Check ✅ "Allow WebRequest for listed URL"
4. Add: `http://localhost:8000`

### 4. Start Volarix 4 API

```bash
cd volarix4
python start.py
```

Wait for: `Uvicorn running on http://0.0.0.0:8000`

### 5. Attach EA to Chart

1. Open a chart (e.g., EURUSD H1)
2. Drag `volarix4` EA onto the chart
3. Configure inputs:

   **Basic Settings:**
   - **SymbolToCheck**: EURUSD
   - **Timeframe**: H1 (or PERIOD_CURRENT)
   - **LookbackBars**: 400
   - **API_URL**: http://localhost:8000
   - **RiskPercent**: 1.0
   - **EnableTrading**: false (for testing)

   **Strategy Parameters** (use defaults initially):
   - **MinConfidence**: 0.60
   - **BrokenLevelCooldownHours**: 48.0
   - **BrokenLevelBreakPips**: 15.0
   - **MinEdgePips**: 4.0

   **Cost Model** (adjust to match your broker):
   - **SpreadPips**: 1.0 (check your broker's spread)
   - **SlippagePips**: 0.5
   - **CommissionPerSidePerLot**: 7.0 (check your broker's commission)
   - **UsdPerPipPerLot**: 10.0
   - **LotSizeForCostCalc**: 1.0

4. Click OK

### 6. Test the Integration

**Check EA Log:**
```
Volarix 4 EA Started - S/R Bounce Strategy
Symbol: EURUSD
Timeframe: H1
...
New H1 candle at 2024-12-25 09:00 - Calling Volarix 4 API...
API Response: Signal=BUY, Confidence=0.75
```

**Check API Log:**
```
[INFO] >> POST /signal
[INFO] Signal request: EURUSD [Single-TF] | Using: exec=H1 | Bars: exec=400
[INFO] Final Signal: BUY (Confidence: 0.75)
[INFO] << POST /signal - Status: 200
```

**Check DLL Debug Log:**
```
File: E:\Volarix4Bridge_Debug.txt

=== Volarix 4 API Call ===
Symbol: EURUSD
Timeframe: H1
Bars: 400
API Response (285 bytes): {"signal":"BUY","confidence":0.75,...
```

## Troubleshooting

### DLL Not Loading
- Check DLL is in `MQL5\Libraries\` folder
- Enable "Allow DLL imports" in MT5
- Check Windows didn't block the DLL (Right-click → Properties → Unblock)

### API Connection Failed
- Verify API is running: `http://localhost:8000/health`
- Check firewall isn't blocking port 8000
- Add URL to WebRequest whitelist in MT5

### No Signals Generated
- Check API logs for errors
- Verify enough bars are available (minimum 400 for trend filter)
- Check if current time is in London/NY session (3-11am or 8am-4pm EST)
- HOLD signals are normal (strategy is selective)

### EA Not Calling API
- Check "AutoTrading" button is enabled in MT5
- Verify EA is attached to chart (smile icon)
- Check EA inputs are correct
- Look at "Experts" tab for error messages

## Input Parameters

### EA Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| SymbolToCheck | EURUSD | Trading symbol |
| Timeframe | PERIOD_H1 | Timeframe for signals |
| LookbackBars | 400 | Bars to send to API |
| API_URL | http://localhost:8000 | Volarix 4 API URL |
| RiskPercent | 1.0 | Risk per trade (%) |
| MaxPositions | 1 | Max concurrent positions |
| EnableTrading | true | Enable auto-trading |

### Strategy Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| MinConfidence | 0.60 | Minimum confidence threshold (0.0-1.0) |
| BrokenLevelCooldownHours | 48.0 | Hours to wait after level breaks (prevents trading broken S/R) |
| BrokenLevelBreakPips | 15.0 | Pips beyond level = broken (larger = more lenient) |
| MinEdgePips | 4.0 | Minimum profitable edge after all costs |

**MinConfidence**: Controls signal quality vs quantity. Higher values (0.70-0.80) = fewer but stronger signals. Lower values (0.55-0.65) = more signals but lower win rate.

**BrokenLevelCooldownHours**: After a support/resistance level is broken (price moves beyond it by BrokenLevelBreakPips), the API waits this many hours before trading that level again. Default 48 hours prevents trading stale levels.

**BrokenLevelBreakPips**: How far price must move beyond a level to consider it "broken". Default 15 pips for major pairs. Adjust based on volatility (use 25-30 for GBP pairs, 10-12 for stable pairs).

**MinEdgePips**: Minimum profit potential after deducting spread, slippage, and commission. Default 4 pips ensures trades have positive expected value. Lower values may result in unprofitable trades due to costs.

### Cost Model Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| SpreadPips | 1.0 | Broker spread in pips (check your broker) |
| SlippagePips | 0.5 | Expected slippage per side (market orders) |
| CommissionPerSidePerLot | 7.0 | USD commission per lot per side |
| UsdPerPipPerLot | 10.0 | Standard lot pip value (typically 10 for majors) |
| LotSizeForCostCalc | 1.0 | Lot size for commission calculation |

**Why These Matter**: The API calculates **net edge** after costs. A trade with 8 pips raw profit but 2 pips spread + 1 pip slippage + 1 pip commission = only 4 pips net edge. If MinEdgePips = 5, this trade is rejected.

**How to Configure**:
1. **SpreadPips**: Check your broker's typical spread for the symbol (Tools → Symbols → Spread)
2. **SlippagePips**: Use 0.5 for ECN brokers, 1.0-2.0 for market makers
3. **CommissionPerSidePerLot**: Check your broker's fee structure (often $3-10/side)
4. **UsdPerPipPerLot**: Usually 10 for majors (EURUSD, GBPUSD), 8-12 for crosses, 1 for JPY pairs
5. **LotSizeForCostCalc**: Set to your typical trade size (1.0 = standard lot, 0.1 = mini lot)

### Strategy Notes

**Volarix 4 vs Volarix 3:**

| Feature | Volarix 3 | Volarix 4 |
|---------|-----------|-----------|
| Strategy | ML Ensemble | S/R Bounce |
| Timeframes | Multi-TF | Single-TF |
| Models | 5 models | No models |
| Complexity | High | Low |
| Speed | Slower | Faster |
| Interpretability | Low | High |

**When to Use Volarix 4:**
- Want simple, transparent strategy
- Don't need multi-timeframe analysis
- Prefer faster response times
- Testing S/R bounce concepts

**When to Use Volarix 3:**
- Need multi-timeframe context
- Want ML model predictions
- Need higher win rate
- Production trading

## Files Overview

### volarix4.mq5 (MQL5 Expert Advisor)

**Key Features:**
- Single-TF only (simplified)
- Pure S/R bounce strategy
- Calls API once per new candle
- Basic trade management
- CSV logging

**Main Functions:**
- `OnInit()` - Initialize EA
- `OnTick()` - Check for new bar → Call API → Execute trades
- `IsNewBar()` - Detect new candle
- `CalculateLotSize()` - Risk-based position sizing

### volarix4_bridge.cpp (C++ DLL)

**Key Features:**
- Converts OHLCV data to JSON
- HTTP POST to `/signal` endpoint
- Returns parsed response to MT5
- Debug logging to `E:\Volarix4Bridge_Debug.txt`

**Flow:**
1. Receive OHLCV bars from MT5
2. Build JSON payload
3. POST to `http://localhost:8000/signal`
4. Receive JSON response
5. Return to MT5

## Development

### Modify Strategy Parameters

Edit `volarix4.mq5` to adjust strategy behavior:
```mql5
// More conservative (fewer, higher quality signals)
input double MinConfidence = 0.75;       // Raise threshold
input double MinEdgePips = 6.0;          // Require more edge

// More aggressive (more signals, lower quality)
input double MinConfidence = 0.55;       // Lower threshold
input double MinEdgePips = 3.0;          // Accept less edge

// Adjust for volatile pairs (GBPJPY, GBPUSD)
input double BrokenLevelBreakPips = 30.0;  // Wider threshold
input double SpreadPips = 2.5;             // Higher typical spread

// Adjust position sizing
input double RiskPercent = 2.0;            // Increase risk per trade
```

### Change API Server

Edit `volarix4_bridge.cpp`:
```cpp
HINTERNET hConnect = InternetConnectA(hInternet,
    "192.168.1.100",  // Your server IP
    8000,             // Port
    ...
```

Recompile DLL and restart MT5.

### Add Custom Indicators

In `volarix4.mq5`, before calling API:
```mql5
// Calculate custom indicator
double ma = iMA(SymbolToCheck, Timeframe, 20, 0, MODE_SMA, PRICE_CLOSE);
// Add to trade logic
```

## Production Deployment

### 1. VPS Setup

1. Install MT5 on VPS
2. Copy DLL to VPS Libraries folder
3. Configure firewall to allow port 8000
4. Run API as Windows service

### 2. API as Service

```bash
# Using NSSM (Non-Sucking Service Manager)
nssm install Volarix4API "C:\Python\python.exe" "E:\volarix4\start.py"
nssm start Volarix4API
```

### 3. Monitor Logs

- EA Log: `MQL5\Logs\`
- CSV Log: `MQL5\Files\volarix4_log.csv`
- API Log: `volarix4\logs\volarix4_YYYY-MM-DD.log`
- DLL Log: `E:\Volarix4Bridge_Debug.txt`

## Support

For issues:
1. Check debug logs
2. Test API independently: `python test_api.py`
3. Verify DLL loads: Check "Experts" tab in MT5
4. Test with EnableTrading=false first

## License

MIT License - Free to use and modify
