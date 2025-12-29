//+------------------------------------------------------------------+
//|                     Volarix 4 - MT5 Expert Advisor              |
//|                  S/R Bounce Strategy - Single Timeframe         |
//|                  Calls API once per new candle                  |
//+------------------------------------------------------------------+
#property copyright "Volarix 4"
#property version   "4.00"
#property strict

//====================================================================
//  OHLCV BAR STRUCTURE (matches API OHLCVBar model)
//====================================================================
struct OHLCVBar
{
   long timestamp;      // Unix timestamp
   double open;
   double high;
   double low;
   double close;
   int volume;
};

//====================================================================
//  IMPORT DLL (DEPRECATED - Now using direct WebRequest)
//====================================================================
// #import "Volarix4Bridge.dll"
//    // Send OHLCV data to Volarix 4 API and get signal
//    string GetVolarix4Signal(
//       string symbol,
//       string timeframe,
//       OHLCVBar &bars[],
//       int barCount
//    );
// #import
// NOTE: DLL is no longer needed. EA now uses MT5's native WebRequest()
// to call the API directly with full strategy parameters.

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
//| Build JSON request body with OHLCV data and strategy params     |
//+------------------------------------------------------------------+
string BuildJSONRequest(MqlRates &rates[], int bar_count)
{
   // Apply backtest parity mode override if enabled
   double min_conf = BacktestParityMode ? 0.60 : MinConfidence;
   double cooldown = BacktestParityMode ? 48.0 : BrokenLevelCooldownHours;
   double break_pips = BacktestParityMode ? 15.0 : BrokenLevelBreakPips;
   double min_edge = BacktestParityMode ? 4.0 : MinEdgePips;
   double spread = BacktestParityMode ? 1.0 : SpreadPips;
   double slippage = BacktestParityMode ? 0.5 : SlippagePips;
   double commission = BacktestParityMode ? 7.0 : CommissionPerSidePerLot;
   double usd_pip = BacktestParityMode ? 10.0 : UsdPerPipPerLot;
   double lot = BacktestParityMode ? 1.0 : LotSize;

   // Start JSON
   string json = "{";
   json += "\"symbol\":\"" + SymbolToCheck + "\",";
   json += "\"timeframe\":\"" + TimeframeToString(Timeframe) + "\",";

   // Add OHLCV bars
   json += "\"data\":[";
   for(int i = 0; i < bar_count; i++)
   {
      if(i > 0) json += ",";
      json += "{";
      json += "\"time\":" + IntegerToString((long)rates[i].time) + ",";
      json += "\"open\":" + DoubleToString(rates[i].open, 5) + ",";
      json += "\"high\":" + DoubleToString(rates[i].high, 5) + ",";
      json += "\"low\":" + DoubleToString(rates[i].low, 5) + ",";
      json += "\"close\":" + DoubleToString(rates[i].close, 5) + ",";
      json += "\"volume\":" + IntegerToString((int)rates[i].tick_volume);
      json += "}";
   }
   json += "],";

   // Add strategy parameters (backtest parity)
   json += "\"min_confidence\":" + DoubleToString(min_conf, 2) + ",";
   json += "\"broken_level_cooldown_hours\":" + DoubleToString(cooldown, 1) + ",";
   json += "\"broken_level_break_pips\":" + DoubleToString(break_pips, 1) + ",";
   json += "\"min_edge_pips\":" + DoubleToString(min_edge, 1) + ",";

   // Add cost model parameters
   json += "\"spread_pips\":" + DoubleToString(spread, 1) + ",";
   json += "\"slippage_pips\":" + DoubleToString(slippage, 1) + ",";
   json += "\"commission_per_side_per_lot\":" + DoubleToString(commission, 1) + ",";
   json += "\"usd_per_pip_per_lot\":" + DoubleToString(usd_pip, 1) + ",";
   json += "\"lot_size\":" + DoubleToString(lot, 2);

   json += "}";

   return json;
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
   Print("Make sure 'Allow Web Requests' is enabled for:");
   Print("  ", API_URL);
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

   datetime current_time = iTime(SymbolToCheck, Timeframe, 0);

   PrintFormat("New %s candle at %s - Calling Volarix 4 API...",
               TimeframeToString(Timeframe),
               TimeToString(current_time, TIME_DATE|TIME_MINUTES));

   // Copy bars from MT5 - CRITICAL: Skip index 0 (forming bar), start from index 1 (last closed bar)
   // Per Parity Contract: API must receive ONLY closed bars
   MqlRates rates[];
   int copied = CopyRates(SymbolToCheck, Timeframe, 1, LookbackBars, rates);

   if(copied <= 0)
   {
      Print("ERROR: Failed to copy bars from MT5");
      return;
   }

   // VALIDATION: Ensure we got the exact number of bars requested
   if(copied != LookbackBars)
   {
      PrintFormat("WARNING: Requested %d bars but got %d bars", LookbackBars, copied);
   }

   // VALIDATION: Check bar ordering, uniqueness, and timeframe alignment
   bool bars_valid = true;
   int timeframe_seconds = PeriodSeconds(Timeframe);

   for(int i = 0; i < copied; i++)
   {
      // Check for time == 0 (invalid bar)
      if(rates[i].time == 0)
      {
         PrintFormat("ERROR: Bar [%d] has time == 0!", i);
         bars_valid = false;
      }

      // Check for strictly increasing timestamps (no duplicates, no gaps)
      if(i > 0)
      {
         long time_delta = (long)rates[i].time - (long)rates[i-1].time;

         if(time_delta <= 0)
         {
            PrintFormat("ERROR: Bars not strictly increasing! Bar[%d] time=%d, Bar[%d] time=%d, delta=%d",
                        i-1, rates[i-1].time, i, rates[i].time, time_delta);
            bars_valid = false;
         }

         // Check timeframe alignment (each bar should be exactly N * timeframe apart)
         if(time_delta % timeframe_seconds != 0)
         {
            PrintFormat("WARNING: Bar[%d] to Bar[%d] delta %d sec is not aligned to timeframe %d sec",
                        i-1, i, time_delta, timeframe_seconds);
         }
      }
   }

   // Check if the last bar is closed (not forming)
   // A forming bar often has open == close with minimal movement
   // The last bar should be at least 1 period old
   datetime last_bar_time = rates[copied-1].time;
   datetime current_server_time = TimeCurrent();
   long last_bar_age_seconds = (long)current_server_time - (long)last_bar_time;

   // Last bar should be at least 1 full timeframe old (closed)
   bool last_bar_closed = (last_bar_age_seconds >= timeframe_seconds);

   if(!last_bar_closed)
   {
      PrintFormat("WARNING: Last bar may be forming! Age: %d sec, Timeframe: %d sec",
                  last_bar_age_seconds, timeframe_seconds);
   }

   // DEBUG: Log first bar, last bar, and bar spacing
   PrintFormat("=== BAR VALIDATION (Parity Contract) ===");
   PrintFormat("  Bars copied: %d (requested: %d)", copied, LookbackBars);
   PrintFormat("  First bar [0]: time=%s (%d)", TimeToString(rates[0].time, TIME_DATE|TIME_SECONDS), rates[0].time);
   PrintFormat("  Last bar [%d]: time=%s (%d)", copied-1, TimeToString(rates[copied-1].time, TIME_DATE|TIME_SECONDS), rates[copied-1].time);

   if(copied >= 2)
   {
      long delta = (long)rates[copied-1].time - (long)rates[copied-2].time;
      PrintFormat("  Delta last 2 bars: %d seconds (expected: %d)", delta, timeframe_seconds);
   }

   PrintFormat("  Last bar age: %d sec (timeframe: %d sec) - Closed: %s",
               last_bar_age_seconds, timeframe_seconds, last_bar_closed ? "YES" : "NO");
   PrintFormat("  Bars validation: %s", bars_valid ? "PASSED" : "FAILED");
   PrintFormat("========================================");

   if(!bars_valid)
   {
      Print("ERROR: Bar validation failed - aborting API call");
      return;
   }

   // Build JSON request with strategy parameters
   Print("Building JSON request with backtest parity parameters...");
   Print("  Symbol: ", SymbolToCheck);
   Print("  Timeframe: ", TimeframeToString(Timeframe));
   Print("  Bars to send: ", copied);

   if(BacktestParityMode)
   {
      Print("  >>> BACKTEST PARITY MODE: Using best backtest params <<<");
      Print("  MinConfidence: 0.60, Cooldown: 48.0h, MinEdge: 4.0 pips");
   }

   string json_request = BuildJSONRequest(rates, copied);

   // Prepare HTTP headers
   string headers = "Content-Type: application/json\r\n";

   // Prepare result arrays
   char post_data[];
   char result_data[];
   string result_headers;

   // Convert JSON string to char array
   StringToCharArray(json_request, post_data, 0, StringLen(json_request), CP_UTF8);

   // Call API using WebRequest
   Print("Calling Volarix 4 API via WebRequest...");
   Print("  URL: ", API_URL, "/signal");

   ResetLastError();
   int timeout = 10000;  // 10 second timeout
   int res = WebRequest(
      "POST",
      API_URL + "/signal",
      headers,
      timeout,
      post_data,
      result_data,
      result_headers
   );

   int web_error = GetLastError();
   if(res == -1)
   {
      PrintFormat("ERROR: WebRequest failed with error code %d", web_error);

      Print("  Make sure:");
      Print("    1. Volarix 4 API is running at: ", API_URL);
      Print("    2. 'Allow WebRequest for listed URL' is enabled in Tools -> Options -> Expert Advisors");
      Print("    3. Add to allowed URLs: ", API_URL);
      return;
   }

   // Convert result to string
   string response = CharArrayToString(result_data, 0, ArraySize(result_data), CP_UTF8);

   if(StringLen(response) == 0)
   {
      Print("WARNING: Empty response from API");
      Print("  HTTP Status Code: ", res);
      Print("  Verify Volarix 4 API is running at: ", API_URL);
      return;
   }

   Print("API Response received (HTTP ", res, ", ", StringLen(response), " bytes)");

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
