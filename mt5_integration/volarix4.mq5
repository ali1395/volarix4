//+------------------------------------------------------------------+
//|                     Volarix 4 - MT5 Expert Advisor              |
//|                  S/R Bounce Strategy - Single Timeframe         |
//|                  Calls API once per new candle                  |
//+------------------------------------------------------------------+
#property copyright "Volarix 4"
#property version   "4.00"
#property strict

//====================================================================
//  IMPORT DLL (Optimized - sends only bar timestamp)
//====================================================================
#import "Volarix4Bridge.dll"
   // Send bar timestamp to Volarix 4 API and get signal
   // API will fetch bars using Python (faster, better correlation with backtest)
   string GetVolarix4Signal(
      string symbol,
      string timeframe,
      long barTime,            // Unix timestamp of bar to generate signal for
      int lookbackBars,        // Number of bars to fetch (e.g., 400)
      string apiUrl,
      double minConfidence,
      double brokenLevelCooldownHours,
      double brokenLevelBreakPips,
      double minEdgePips,
      double spreadPips,
      double slippagePips,
      double commissionPerSidePerLot,
      double usdPerPipPerLot,
      double lotSize
   );
#import

//====================================================================
//  INPUT PARAMETERS
//====================================================================
input string SymbolToCheck = "EURUSD";           // Symbol to trade
input ENUM_TIMEFRAMES Timeframe = PERIOD_H1;     // Timeframe
input int    LookbackBars  = 400;                // Number of bars to send to API
input string API_URL = "http://localhost:8000";  // Volarix 4 API URL

// Trade Management
input double RiskPercent = 1.0;                  // Risk per trade (%)
input int    MaxPositions = 1;                   // Max open positions
input bool   EnableTrading = true;               // Enable auto-trading

// Backtest Parity Mode (force best backtest parameters)
input bool   BacktestParityMode = true;          // Force best backtest params & log them

// Strategy Parameters (matching tests/backtest.py for comparable results)
input double MinConfidence = 0.60;               // Minimum rejection confidence (best: 0.60)
input double BrokenLevelCooldownHours = 48.0;    // Broken level cooldown in hours (best: 48.0)
input double BrokenLevelBreakPips = 15.0;        // Pips to consider level broken (default: 15.0)
input double MinEdgePips = 4.0;                  // Minimum edge after costs (best: 4.0)

// Cost Model Parameters (for min_edge calculation matching Python backtest)
input double SpreadPips = 1.0;                   // Broker spread in pips
input double SlippagePips = 0.5;                 // Estimated slippage per trade (one-way)
input double CommissionPerSidePerLot = 7.0;      // Commission in USD per side per lot
input double UsdPerPipPerLot = 10.0;             // USD value per pip per lot (standard forex)
input double LotSize = 1.0;                      // Lot size for commission calculation

//====================================================================
//  GLOBAL VARIABLES
//====================================================================
datetime last_bar_time = 0;        // Time of last processed bar
int log_handle = INVALID_HANDLE;   // File handle for logging

//====================================================================
//  HELPER FUNCTIONS
//====================================================================

//+------------------------------------------------------------------+
//| Convert ENUM_TIMEFRAMES to API string format                     |
//+------------------------------------------------------------------+
string TimeframeToString(ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      case PERIOD_W1:  return "W1";
      default:         return "H1";
   }
}

//+------------------------------------------------------------------+
//| Write to log file                                                 |
//+------------------------------------------------------------------+
void WriteToLog(string message)
{
   if(log_handle == INVALID_HANDLE)
   {
      log_handle = FileOpen("volarix4_log.csv", FILE_WRITE|FILE_READ|FILE_CSV|FILE_ANSI, ',');

      if(log_handle == INVALID_HANDLE)
      {
         Print("Failed to open log file");
         return;
      }

      // Write header
      if(FileSize(log_handle) == 0)
      {
         FileWrite(log_handle, "Timestamp", "Symbol", "Signal", "Confidence",
                   "Entry", "SL", "TP1", "TP2", "TP3", "Reason", "Ticket", "Status");
      }
   }

   FileSeek(log_handle, 0, SEEK_END);
   FileWriteString(log_handle, message + "\n");
   FileFlush(log_handle);
}

//+------------------------------------------------------------------+
//| Get current open positions count                                 |
//+------------------------------------------------------------------+
int GetOpenPositionsCount()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == SymbolToCheck)
         count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| Calculate lot size based on risk percentage                      |
//+------------------------------------------------------------------+
double CalculateLotSize(double entry, double sl)
{
   double risk_amount = AccountInfoDouble(ACCOUNT_BALANCE) * (RiskPercent / 100.0);
   double sl_distance = MathAbs(entry - sl);
   double tick_value = SymbolInfoDouble(SymbolToCheck, SYMBOL_TRADE_TICK_VALUE);
   double tick_size = SymbolInfoDouble(SymbolToCheck, SYMBOL_TRADE_TICK_SIZE);

   double lot_size = risk_amount / (sl_distance / tick_size * tick_value);

   // Normalize to broker's lot step
   double min_lot = SymbolInfoDouble(SymbolToCheck, SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(SymbolToCheck, SYMBOL_VOLUME_MAX);
   double lot_step = SymbolInfoDouble(SymbolToCheck, SYMBOL_VOLUME_STEP);

   lot_size = MathFloor(lot_size / lot_step) * lot_step;
   lot_size = MathMax(min_lot, MathMin(max_lot, lot_size));

   return lot_size;
}

//====================================================================
//  INITIALIZATION
//====================================================================
int OnInit()
{
   Print("=================================================");
   Print("Volarix 4 EA Started - S/R Bounce Strategy");
   Print("=================================================");
   Print("Symbol: ", SymbolToCheck);
   Print("Timeframe: ", TimeframeToString(Timeframe));
   Print("Lookback Bars: ", LookbackBars);
   Print("API URL: ", API_URL);
   Print("Auto-Trading: ", EnableTrading ? "ENABLED" : "DISABLED");
   Print("Risk per Trade: ", RiskPercent, "%");
   Print("=================================================");
   Print("Strategy: Pure S/R bounce (no ML models)");
   Print("Mode: Single-TF only");
   Print("Backtest Parity Mode: ", BacktestParityMode ? "ENABLED" : "DISABLED");
   Print("=================================================");

   // Display strategy parameters (with backtest parity override if enabled)
   double active_min_conf = BacktestParityMode ? 0.60 : MinConfidence;
   double active_cooldown = BacktestParityMode ? 48.0 : BrokenLevelCooldownHours;
   double active_break_pips = BacktestParityMode ? 15.0 : BrokenLevelBreakPips;
   double active_min_edge = BacktestParityMode ? 4.0 : MinEdgePips;
   double active_spread = BacktestParityMode ? 1.0 : SpreadPips;
   double active_slippage = BacktestParityMode ? 0.5 : SlippagePips;
   double active_commission = BacktestParityMode ? 7.0 : CommissionPerSidePerLot;
   double active_usd_pip = BacktestParityMode ? 10.0 : UsdPerPipPerLot;
   double active_lot = BacktestParityMode ? 1.0 : LotSize;

   if(BacktestParityMode)
   {
      Print("*** BACKTEST PARITY MODE ACTIVE ***");
      Print("Forcing best backtest parameters (overriding inputs):");
   }
   else
   {
      Print("Strategy Parameters (from inputs):");
   }

   Print("  MinConfidence: ", active_min_conf);
   Print("  BrokenLevelCooldownHours: ", active_cooldown);
   Print("  BrokenLevelBreakPips: ", active_break_pips);
   Print("  MinEdgePips: ", active_min_edge);
   Print("Cost Model:");
   Print("  SpreadPips: ", active_spread);
   Print("  SlippagePips: ", active_slippage);
   Print("  CommissionPerSidePerLot: $", active_commission);
   Print("  UsdPerPipPerLot: $", active_usd_pip);
   Print("  LotSize: ", active_lot);
   Print("=================================================");
   Print("Make sure 'Allow DLL imports' is enabled");
   Print("Volarix4Bridge.dll must be in MQL5\\Libraries\\");
   Print("=================================================");

   last_bar_time = iTime(SymbolToCheck, Timeframe, 0);

   return(INIT_SUCCEEDED);
}

//====================================================================
//  NEW BAR DETECTION
//====================================================================
bool IsNewBar()
{
   datetime current_bar_time = iTime(SymbolToCheck, Timeframe, 0);

   if(current_bar_time != last_bar_time)
   {
      last_bar_time = current_bar_time;
      return true;
   }

   return false;
}

//====================================================================
//  ON TICK - MAIN LOGIC
//====================================================================
void OnTick()
{
   // Only call API on new bar
   if(!IsNewBar())
      return;

   // Get the bar time we want to generate signal for (current bar at index 0)
   datetime current_bar_time = iTime(SymbolToCheck, Timeframe, 0);
   long bar_timestamp = (long)current_bar_time;

   PrintFormat("New %s candle at %s - Calling Volarix 4 API (Optimized Mode)...",
               TimeframeToString(Timeframe),
               TimeToString(current_bar_time, TIME_DATE|TIME_MINUTES));

   PrintFormat("Sending bar timestamp: %d (API will fetch bars using Python)", bar_timestamp);

   // Determine active parameters (backtest parity mode or user inputs)
   double active_min_conf = BacktestParityMode ? 0.60 : MinConfidence;
   double active_cooldown = BacktestParityMode ? 48.0 : BrokenLevelCooldownHours;
   double active_break_pips = BacktestParityMode ? 15.0 : BrokenLevelBreakPips;
   double active_min_edge = BacktestParityMode ? 4.0 : MinEdgePips;
   double active_spread = BacktestParityMode ? 1.0 : SpreadPips;
   double active_slippage = BacktestParityMode ? 0.5 : SlippagePips;
   double active_commission = BacktestParityMode ? 7.0 : CommissionPerSidePerLot;
   double active_usd_pip = BacktestParityMode ? 10.0 : UsdPerPipPerLot;
   double active_lot = BacktestParityMode ? 1.0 : LotSize;

   Print("Calling DLL: GetVolarix4Signal() [Optimized Mode]");
   Print("  Symbol: ", SymbolToCheck);
   Print("  Timeframe: ", TimeframeToString(Timeframe));
   Print("  Bar timestamp: ", bar_timestamp);
   Print("  Lookback bars: ", LookbackBars);
   Print("  Min Confidence: ", active_min_conf);
   Print("  Min Edge (pips): ", active_min_edge);

   // Call DLL to get signal from API (optimized - only send bar timestamp)
   ResetLastError();
   string response = GetVolarix4Signal(
      SymbolToCheck,
      TimeframeToString(Timeframe),
      bar_timestamp,        // Only send bar timestamp
      LookbackBars,         // Number of bars to fetch
      API_URL,
      active_min_conf,
      active_cooldown,
      active_break_pips,
      active_min_edge,
      active_spread,
      active_slippage,
      active_commission,
      active_usd_pip,
      active_lot
   );

   int dll_error = GetLastError();
   if(dll_error != 0)
   {
      PrintFormat("ERROR: DLL call failed with error code %d", dll_error);

      Print("  Make sure:");
      Print("    1. Volarix4Bridge.dll is in [MT5 Data Folder]\\MQL5\\Libraries\\");
      Print("    2. 'Allow DLL imports' is enabled in Tools -> Options -> Expert Advisors");
      Print("    3. The DLL was compiled for x64 architecture");
      Print("    4. Volarix 4 API is running at: ", API_URL);
      return;
   }

   if(StringLen(response) == 0)
   {
      Print("WARNING: Empty response from API");
      Print("  HTTP Status Code: ", response);
      Print("  Verify Volarix 4 API is running at: ", API_URL);
      return;
   }

   Print("API Response received (HTTP ", response, ", ", StringLen(response), " bytes)");

   // Parse JSON response (simplified - in production use proper JSON parser)
   // Expected: {"signal":"BUY","confidence":0.75,"entry":1.08520,"sl":1.08390,
   //            "tp1":1.08650,"tp2":1.08780,"tp3":1.08910,"reason":"..."}

   string signal = "";
   double confidence = 0.0;
   double entry = 0.0;
   double sl = 0.0;
   double tp1 = 0.0;
   double tp2 = 0.0;
   double tp3 = 0.0;
   string reason = "";

   // Simple JSON parsing (you may want to use a proper JSON library)
   if(StringFind(response, "\"signal\":\"BUY\"") >= 0)
      signal = "BUY";
   else if(StringFind(response, "\"signal\":\"SELL\"") >= 0)
      signal = "SELL";
   else if(StringFind(response, "\"signal\":\"HOLD\"") >= 0)
      signal = "HOLD";

   // Extract numeric values from JSON
   int conf_pos = StringFind(response, "\"confidence\":");
   if(conf_pos >= 0)
   {
      string conf_str = StringSubstr(response, conf_pos + 14, 10);
      confidence = StringToDouble(conf_str);
   }

   int entry_pos = StringFind(response, "\"entry\":");
   if(entry_pos >= 0)
   {
      string entry_str = StringSubstr(response, entry_pos + 8, 15);
      entry = StringToDouble(entry_str);
   }

   int sl_pos = StringFind(response, "\"sl\":");
   if(sl_pos >= 0)
   {
      string sl_str = StringSubstr(response, sl_pos + 5, 15);
      sl = StringToDouble(sl_str);
   }

   int tp2_pos = StringFind(response, "\"tp2\":");
   if(tp2_pos >= 0)
   {
      string tp2_str = StringSubstr(response, tp2_pos + 6, 15);
      tp2 = StringToDouble(tp2_str);
   }

   PrintFormat("API Response: Signal=%s, Confidence=%.2f, Entry=%.5f, SL=%.5f, TP=%.5f",
               signal, confidence, entry, sl, tp2);

   // Execute trade if signal is BUY or SELL
   if(EnableTrading && (signal == "BUY" || signal == "SELL"))
   {
      // Check if we already have max positions
      if(GetOpenPositionsCount() >= MaxPositions)
      {
         Print("Max positions reached. Skipping trade.");
         return;
      }

      // Validate API provided values
      if(entry == 0.0 || sl == 0.0 || tp2 == 0.0)
      {
         Print("ERROR: Invalid trade parameters from API (entry/sl/tp cannot be 0)");
         Print("  Entry: ", entry, ", SL: ", sl, ", TP: ", tp2);
         return;
      }

      // Calculate lot size using API's entry and SL
      double lot = CalculateLotSize(entry, sl);

      // Use current market price for execution (not API's entry)
      double current_price = (signal == "BUY") ?
         SymbolInfoDouble(SymbolToCheck, SYMBOL_ASK) :
         SymbolInfoDouble(SymbolToCheck, SYMBOL_BID);

      PrintFormat("Opening trade: %s at %.5f, SL=%.5f, TP=%.5f, Lot=%.2f",
                  signal, current_price, sl, tp2, lot);

      // Open trade
      MqlTradeRequest request = {};
      MqlTradeResult result = {};

      request.action = TRADE_ACTION_DEAL;
      request.symbol = SymbolToCheck;
      request.volume = lot;
      request.type = (signal == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      request.price = current_price;
      request.sl = sl;        // Use API's SL
      request.tp = tp2;       // Use API's TP2 (main target)
      request.deviation = 10;
      request.magic = 20241225;
      request.comment = "Volarix4 S/R";

      if(OrderSend(request, result))
      {
         PrintFormat("Trade opened: Ticket=%d, Price=%.5f, SL=%.5f, TP=%.5f, Lot=%.2f",
                     result.order, result.price, sl, tp2, lot);

         // Log to CSV
         string log_line = StringFormat("%s,%s,%s,%.2f,%.5f,%.5f,%.5f,0,0,%s,%d,SUCCESS",
                                        TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
                                        SymbolToCheck, signal, confidence,
                                        result.price, sl, tp2, reason, result.order);
         WriteToLog(log_line);
      }
      else
      {
         PrintFormat("Trade failed: Error=%d, Retcode=%d", GetLastError(), result.retcode);
      }
   }
   else if(signal == "HOLD")
   {
      Print("Signal: HOLD - No trade opportunity");
   }
}

//====================================================================
//  ON DEINIT
//====================================================================
void OnDeinit(const int reason)
{
   if(log_handle != INVALID_HANDLE)
   {
      FileClose(log_handle);
      log_handle = INVALID_HANDLE;
   }

   Print("Volarix 4 EA stopped");
}
