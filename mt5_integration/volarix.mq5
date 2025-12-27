//+------------------------------------------------------------------+
//|               VolariX API DLL Bridge Expert (MQL5)               |
//|                    With Real OHLCV Data from MT5                 |
//|                    Calls API once per new candle                 |
//+------------------------------------------------------------------+
#property copyright "VolariX"
#property version   "3.00"
#property strict

//====================================================================
//  OHLCV BAR STRUCTURE (must be defined before DLL import)
//====================================================================
struct OHLCVBar
{
   char timestamp[32];
   double open;
   double high;
   double low;
   double close;
   double volume;
};

//====================================================================
//  IMPORT DLL - Two versions available
//====================================================================
#import "VolariXBridge.dll"
// Simple version with mock data + time range (for testing only)
// string GetVolariXSignal(string symbol, string startTime, string endTime);

// Advanced version with actual OHLCV data (PRODUCTION VERSION - NOW ACTIVE)
// Multi-timeframe version: accepts both execution and context timeframes
string GetVolariXSignalWithBars(
   string symbol,
   string timeframe,
   OHLCVBar &bars[],
   int barCount,
   string startTime,
   string endTime,
   string executionTimeframe,  // NEW: Explicit execution timeframe
   string contextTimeframe,    // NEW: Context timeframe (empty string = single-TF mode)
   OHLCVBar &contextBars[],    // NEW: Context bars array (can be empty)
   int contextBarCount         // NEW: Context bar count (0 = single-TF mode)
);
#import

//====================================================================
//  INPUT PARAMETERS
//====================================================================
input string SymbolToCheck = "EURUSD";   // Symbol to request
input int    LookbackBars  = 400;         // Number of bars to send to API (minimum 200 for Ichimoku features)
input ENUM_TIMEFRAMES ExecutionTimeframe = PERIOD_CURRENT;  // Execution timeframe (signal generation)
input ENUM_TIMEFRAMES ContextTimeframe = PERIOD_CURRENT;    // Context timeframe (regime/trend analysis, set to PERIOD_CURRENT to disable)

//====================================================================
//  GLOBAL VARIABLES
//====================================================================
datetime last_bar_time = 0;  // Time of last processed bar
int log_handle = INVALID_HANDLE;  // File handle for detailed logging

//====================================================================
//  HELPER FUNCTIONS
//====================================================================

//+------------------------------------------------------------------+
//| Convert datetime to ISO 8601 format (UTC)                        |
//+------------------------------------------------------------------+
string DateTimeToISO8601(datetime dt)
{
   MqlDateTime mdt;
   TimeToStruct(dt, mdt);

   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                       mdt.year, mdt.mon, mdt.day,
                       mdt.hour, mdt.min, mdt.sec);
}

//+------------------------------------------------------------------+
//| Get timeframe as string (e.g., "1h", "4h", "1d")                |
//+------------------------------------------------------------------+
string TimeframeToString(ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M1:  return "1m";
      case PERIOD_M5:  return "5m";
      case PERIOD_M15: return "15m";
      case PERIOD_M30: return "30m";
      case PERIOD_H1:  return "1h";
      case PERIOD_H4:  return "4h";
      case PERIOD_D1:  return "1d";
      case PERIOD_W1:  return "1w";
      default:         return "1h";
   }
}

//+------------------------------------------------------------------+
//| Write to detailed log file                                        |
//+------------------------------------------------------------------+
void WriteToLog(string message)
{
   if(log_handle == INVALID_HANDLE)
   {
      // Open log file in append mode
      log_handle = FileOpen("volarix_execution_log.csv", FILE_WRITE|FILE_READ|FILE_CSV|FILE_ANSI, ',');

      if(log_handle == INVALID_HANDLE)
      {
         Print("❌ Failed to open log file: ", GetLastError());
         return;
      }

      // Write header if file is new
      if(FileSize(log_handle) == 0)
      {
         FileWrite(log_handle, "Timestamp", "Trace_ID", "Symbol", "Signal", "Score", "Confidence",
                   "Entry", "SL", "TP", "Status", "Error_Code", "Error_Message", "Ticket");
      }
   }

   FileSeek(log_handle, 0, SEEK_END);
   FileWriteString(log_handle, message + "\n");
   FileFlush(log_handle);
}

//+------------------------------------------------------------------+
//| Log signal details to CSV file                                    |
//+------------------------------------------------------------------+
void LogSignalExecution(string trace_id, string symbol, string signal, double score,
                        double confidence, double entry, double sl, double tp,
                        string status, int error_code, string error_msg, long ticket)
{
   string timestamp = TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS);

   string log_line = StringFormat("%s,%s,%s,%s,%.4f,%.4f,%.5f,%.5f,%.5f,%s,%d,%s,%lld",
                                   timestamp, trace_id, symbol, signal, score, confidence,
                                   entry, sl, tp, status, error_code, error_msg, ticket);

   WriteToLog(log_line);
}

//+------------------------------------------------------------------+
//| Calculate lookback period in hours based on timeframe and bars  |
//+------------------------------------------------------------------+
int CalculateLookbackHours(ENUM_TIMEFRAMES tf, int bars)
{
   int minutes_per_bar = PeriodSeconds(tf) / 60;
   return (minutes_per_bar * bars) / 60;
}

//====================================================================
//  INITIALIZATION
//====================================================================
int OnInit()
{
   Print("🚀 VolariX DLL Expert v3.0 started (PRODUCTION MODE - Real OHLCV Data)");
   Print("   Symbol: ", SymbolToCheck);
   Print("   Execution Timeframe: ", TimeframeToString(ExecutionTimeframe));

   // Determine if multi-TF mode is enabled
   bool isMultiTF = (ContextTimeframe != ExecutionTimeframe && ContextTimeframe != PERIOD_CURRENT);
   if(isMultiTF)
   {
      Print("   Context Timeframe: ", TimeframeToString(ContextTimeframe), " (Multi-TF mode enabled)");
   }
   else
   {
      Print("   Context Timeframe: DISABLED (Single-TF mode)");
   }

   Print("   Lookback bars: ", LookbackBars);
   Print("   Mode: Call API once per new candle with real market data");
   Print("   Make sure 'Allow DLL imports' is enabled for this EA");

   // Initialize with current bar time from execution timeframe
   last_bar_time = iTime(SymbolToCheck, ExecutionTimeframe, 0);

   return(INIT_SUCCEEDED);
}

//====================================================================
//  NEW BAR DETECTION
//====================================================================
bool IsNewBar()
{
   datetime current_bar_time = iTime(SymbolToCheck, ExecutionTimeframe, 0);

   if(current_bar_time != last_bar_time)
   {
      last_bar_time = current_bar_time;
      return true;
   }

   return false;
}

//====================================================================
//  ON TICK EVENT - PRODUCTION VERSION WITH REAL OHLCV DATA
//====================================================================
void OnTick()
{
   // Check if a new bar has opened
   if(!IsNewBar())
      return;  // Exit if not a new bar

   datetime current_time = iTime(SymbolToCheck, ExecutionTimeframe, 0);

   // Determine if multi-TF mode is enabled
   bool isMultiTF = (ContextTimeframe != ExecutionTimeframe && ContextTimeframe != PERIOD_CURRENT);

   string mode_str = isMultiTF ? "Multi-TF" : "Single-TF";
   PrintFormat("📊 New %s candle opened at %s - Calling VolariX API (%s mode)...",
               TimeframeToString(ExecutionTimeframe),
               TimeToString(current_time, TIME_DATE|TIME_MINUTES),
               mode_str);

   // Copy execution timeframe bars
   MqlRates exec_rates[];
   int exec_copied = CopyRates(SymbolToCheck, ExecutionTimeframe, 0, LookbackBars, exec_rates);

   if(exec_copied <= 0)
   {
      Print("⚠️ Failed to copy execution timeframe bars from MT5");
      return;
   }

   // Convert execution bars to OHLCVBar array
   OHLCVBar exec_bars[];
   ArrayResize(exec_bars, exec_copied);

   datetime exec_start_time = exec_rates[0].time;
   datetime exec_end_time = exec_rates[exec_copied-1].time;

   for(int i = 0; i < exec_copied; i++)
   {
      string ts = DateTimeToISO8601(exec_rates[i].time);

      // Clear the timestamp array to avoid garbage data
      for(int j = 0; j < 32; j++)
         exec_bars[i].timestamp[j] = 0;

      // Copy string to char array
      int len = StringLen(ts);
      if(len > 31) len = 31;
      StringToCharArray(ts, exec_bars[i].timestamp, 0, len);

      exec_bars[i].open = exec_rates[i].open;
      exec_bars[i].high = exec_rates[i].high;
      exec_bars[i].low = exec_rates[i].low;
      exec_bars[i].close = exec_rates[i].close;
      exec_bars[i].volume = (double)exec_rates[i].tick_volume;
   }

   // Handle context timeframe bars (if multi-TF mode)
   OHLCVBar ctx_bars[];
   int ctx_copied = 0;
   string ctx_tf_str = "";

   if(isMultiTF)
   {
      MqlRates ctx_rates[];
      ctx_copied = CopyRates(SymbolToCheck, ContextTimeframe, 0, LookbackBars, ctx_rates);

      if(ctx_copied > 0)
      {
         ArrayResize(ctx_bars, ctx_copied);

         for(int i = 0; i < ctx_copied; i++)
         {
            string ts = DateTimeToISO8601(ctx_rates[i].time);

            for(int j = 0; j < 32; j++)
               ctx_bars[i].timestamp[j] = 0;

            int len = StringLen(ts);
            if(len > 31) len = 31;
            StringToCharArray(ts, ctx_bars[i].timestamp, 0, len);

            ctx_bars[i].open = ctx_rates[i].open;
            ctx_bars[i].high = ctx_rates[i].high;
            ctx_bars[i].low = ctx_rates[i].low;
            ctx_bars[i].close = ctx_rates[i].close;
            ctx_bars[i].volume = (double)ctx_rates[i].tick_volume;
         }

         ctx_tf_str = TimeframeToString(ContextTimeframe);
         PrintFormat("   Context bars copied: %d (%s)", ctx_copied, ctx_tf_str);
      }
      else
      {
         Print("⚠️ Failed to copy context timeframe bars - falling back to single-TF mode");
         isMultiTF = false;
      }
   }

   string start_time_str = DateTimeToISO8601(exec_start_time);
   string end_time_str = DateTimeToISO8601(exec_end_time);
   string exec_tf_str = TimeframeToString(ExecutionTimeframe);

   PrintFormat("   Execution bars: %d (%s)", exec_copied, exec_tf_str);
   PrintFormat("   Time range: %s to %s", start_time_str, end_time_str);

   // Call DLL with execution and optional context bars
   string response = GetVolariXSignalWithBars(
      SymbolToCheck,
      exec_tf_str,              // Backward compat: timeframe field
      exec_bars,
      exec_copied,
      start_time_str,
      end_time_str,
      exec_tf_str,              // NEW: Explicit execution timeframe
      ctx_tf_str,               // NEW: Context timeframe (empty if single-TF)
      ctx_bars,                 // NEW: Context bars (empty array if single-TF)
      ctx_copied                // NEW: Context bar count (0 if single-TF)
   );

   if(StringLen(response) == 0)
   {
      Print("⚠️ Empty response from DLL.");
      return;
   }

   ParseAndDisplayResponse(response);
}

//====================================================================
//  SIGNAL DATA STRUCTURE
//====================================================================
struct SignalData
{
   string decision_id;      // Unique decision ID for trade tracking
   string symbol;
   string signal;           // buy, sell, hold
   double score;
   double confidence;
   double entry;
   double stop_loss;
   double take_profit;
   string timestamp;
   string trace_id;
};

//====================================================================
//  PARSE AND DISPLAY API RESPONSE
//====================================================================
void ParseAndDisplayResponse(string response)
{
   Print("📡 Response received:");

   SignalData signal_data;

   if(ParseJSONResponse(response, signal_data))
   {
      // Display parsed signal
      Print("✅ Signal Parsed Successfully:");
      Print("   Decision ID: ", signal_data.decision_id);
      Print("   Symbol: ", signal_data.symbol);
      Print("   Signal: ", signal_data.signal);
      Print("   Score: ", signal_data.score);
      Print("   Confidence: ", signal_data.confidence);

      if(signal_data.signal != "hold")
      {
         Print("   Entry: ", signal_data.entry);
         Print("   Stop Loss: ", signal_data.stop_loss);
         Print("   Take Profit: ", signal_data.take_profit);
      }

      // Execute trade if signal is buy or sell
      if(signal_data.signal == "buy" || signal_data.signal == "sell")
      {
         ExecuteTrade(signal_data);
      }
      else if(signal_data.signal == "hold")
      {
         // Log hold signals
         LogSignalExecution(signal_data.trace_id, signal_data.symbol, signal_data.signal,
                           signal_data.score, signal_data.confidence, signal_data.entry,
                           signal_data.stop_loss, signal_data.take_profit,
                           "HOLD_SIGNAL", 0, "Signal was hold, no trade executed", 0);
         Print("⚪ HOLD signal - No trade executed");
      }
      else
      {
         // Log unknown signals
         LogSignalExecution(signal_data.trace_id, signal_data.symbol, signal_data.signal,
                           signal_data.score, signal_data.confidence, signal_data.entry,
                           signal_data.stop_loss, signal_data.take_profit,
                           "UNKNOWN_SIGNAL", 0, "Unrecognized signal type", 0);
         Print("⚠️ Unknown signal type: ", signal_data.signal);
      }
   }
   else
   {
      Print("⚠️ Failed to parse JSON response");
      Print(response);
   }
}

//====================================================================
//  JSON PARSER - Simple key-value extraction
//====================================================================
bool ParseJSONResponse(string json, SignalData &signal_data)
{
   // Extract decision_id
   signal_data.decision_id = ExtractStringValue(json, "decision_id");
   if(signal_data.decision_id == "")
      return false;

   // Extract symbol
   signal_data.symbol = ExtractStringValue(json, "symbol");

   // Extract signal
   signal_data.signal = ExtractStringValue(json, "signal");
   if(signal_data.signal == "")
      return false;

   // Extract numeric values
   signal_data.score = ExtractDoubleValue(json, "score");
   signal_data.confidence = ExtractDoubleValue(json, "confidence");
   signal_data.entry = ExtractDoubleValue(json, "entry");
   signal_data.stop_loss = ExtractDoubleValue(json, "stop_loss");
   signal_data.take_profit = ExtractDoubleValue(json, "take_profit");

   // Extract timestamp and trace_id
   signal_data.timestamp = ExtractStringValue(json, "timestamp");
   signal_data.trace_id = ExtractStringValue(json, "trace_id");

   return true;
}

//====================================================================
//  EXTRACT STRING VALUE FROM JSON
//====================================================================
string ExtractStringValue(string json, string key)
{
   string search_key = "\"" + key + "\":";
   int start_pos = StringFind(json, search_key);

   if(start_pos < 0)
      return "";

   start_pos += StringLen(search_key);

   // Skip whitespace
   while(start_pos < StringLen(json) && StringGetCharacter(json, start_pos) == ' ')
      start_pos++;

   // Check if value is quoted
   bool is_quoted = false;
   if(start_pos < StringLen(json) && StringGetCharacter(json, start_pos) == '"')
   {
      is_quoted = true;
      start_pos++;  // Skip opening quote
   }

   // Find end of value
   int end_pos = start_pos;
   while(end_pos < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, end_pos);

      if(is_quoted)
      {
         // If quoted, stop at closing quote
         if(ch == '"')
            break;
      }
      else
      {
         // If not quoted, stop at comma or closing brace
         if(ch == ',' || ch == '}')
            break;
      }
      end_pos++;
   }

   string value = StringSubstr(json, start_pos, end_pos - start_pos);

   // Trim whitespace
   StringTrimLeft(value);
   StringTrimRight(value);

   return value;
}

//====================================================================
//  EXTRACT DOUBLE VALUE FROM JSON
//====================================================================
double ExtractDoubleValue(string json, string key)
{
   string search_key = "\"" + key + "\":";
   int start_pos = StringFind(json, search_key);

   if(start_pos < 0)
      return 0.0;

   start_pos += StringLen(search_key);

   // Skip whitespace
   while(start_pos < StringLen(json) && StringGetCharacter(json, start_pos) == ' ')
      start_pos++;

   // Handle null values
   if(StringSubstr(json, start_pos, 4) == "null")
      return 0.0;

   // Extract number
   int end_pos = start_pos;
   while(end_pos < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, end_pos);
      if(ch == ',' || ch == '}' || ch == ' ')
         break;
      end_pos++;
   }

   string value = StringSubstr(json, start_pos, end_pos - start_pos);
   return StringToDouble(value);
}

//====================================================================
//  EXECUTE TRADE BASED ON SIGNAL
//====================================================================
void ExecuteTrade(SignalData &signal_data)
{
   Print("💰 Executing trade based on signal...");
   Print("   Decision ID: ", signal_data.decision_id, " (will be used as comment)");
   Print("   Symbol: ", signal_data.symbol);
   Print("   Signal: ", signal_data.signal);

   // Prepare trade request
   MqlTradeRequest request;
   MqlTradeResult result;
   ZeroMemory(request);
   ZeroMemory(result);

   // Set trade parameters
   request.action = TRADE_ACTION_DEAL;
   request.symbol = signal_data.symbol;           // Use symbol from API response
   request.volume = 0.01;                         // Fixed volume (can be made configurable)
   request.type = (signal_data.signal == "buy") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   request.price = (signal_data.signal == "buy") ? SymbolInfoDouble(signal_data.symbol, SYMBOL_ASK)
                                                  : SymbolInfoDouble(signal_data.symbol, SYMBOL_BID);
   request.sl = signal_data.stop_loss;
   request.tp = signal_data.take_profit;
   request.deviation = 10;                        // Max price deviation in points
   request.magic = 123456;                        // Magic number for EA identification
   request.comment = signal_data.trace_id;     // ✅ Use trace_id as comment for tracking!
   request.type_filling = ORDER_FILLING_FOK;      // Fill or Kill

   // Send order
   Print("📤 Sending order to MT5...");
   Print("   Type: ", (request.type == ORDER_TYPE_BUY ? "BUY" : "SELL"));
   Print("   Volume: ", request.volume);
   Print("   Price: ", request.price);
   Print("   SL: ", request.sl);
   Print("   TP: ", request.tp);

   if(OrderSend(request, result))
   {
      if(result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED)
      {
         Print("✅ Trade executed successfully!");
         Print("   Ticket: ", result.order);
         Print("   Fill Price: ", result.price);
         Print("   Volume: ", result.volume);
         Print("   Trace ID: ", signal_data.trace_id);

         // Log successful execution
         LogSignalExecution(signal_data.trace_id, signal_data.symbol, signal_data.signal,
                           signal_data.score, signal_data.confidence, signal_data.entry,
                           signal_data.stop_loss, signal_data.take_profit,
                           "EXECUTED", result.retcode, "Trade executed successfully", result.order);

         // TODO: Report execution back to VolariX API
         // ReportTradeExecution(signal_data.trace_id, result.order, "executed", ...);
      }
      else
      {
         Print("⚠️ Order placed but returned code: ", result.retcode);
         Print("   Comment: ", result.comment);

         // Log with warning
         LogSignalExecution(signal_data.trace_id, signal_data.symbol, signal_data.signal,
                           signal_data.score, signal_data.confidence, signal_data.entry,
                           signal_data.stop_loss, signal_data.take_profit,
                           "PARTIAL_SUCCESS", result.retcode, result.comment, result.order);
      }
   }
   else
   {
      Print("❌ Trade execution failed!");
      Print("   Error code: ", result.retcode);
      Print("   Comment: ", result.comment);

      string error_description = "";

      // Common error codes
      switch(result.retcode)
      {
         case TRADE_RETCODE_INVALID:
            error_description = "Invalid request";
            Print("   → Invalid request");
            break;
         case TRADE_RETCODE_INVALID_VOLUME:
            error_description = "Invalid volume";
            Print("   → Invalid volume");
            break;
         case TRADE_RETCODE_INVALID_PRICE:
            error_description = "Invalid price";
            Print("   → Invalid price");
            break;
         case TRADE_RETCODE_INVALID_STOPS:
            error_description = "Invalid stops (SL/TP)";
            Print("   → Invalid stops (SL/TP)");
            break;
         case TRADE_RETCODE_NO_MONEY:
            error_description = "Not enough money";
            Print("   → Not enough money");
            break;
         case TRADE_RETCODE_MARKET_CLOSED:
            error_description = "Market is closed";
            Print("   → Market is closed");
            break;
         case TRADE_RETCODE_TRADE_DISABLED:
            error_description = "Trading is disabled";
            Print("   → Trading is disabled");
            break;
         default:
            error_description = "Unknown error: " + result.comment;
            Print("   → Unknown error");
      }

      // Log failed execution
      LogSignalExecution(signal_data.trace_id, signal_data.symbol, signal_data.signal,
                        signal_data.score, signal_data.confidence, signal_data.entry,
                        signal_data.stop_loss, signal_data.take_profit,
                        "FAILED", result.retcode, error_description, 0);

      // TODO: Report failed execution to VolariX API
      // ReportTradeExecution(signal_data.trace_id, 0, "failed", ...);
   }
}

//====================================================================
//  DEINITIALIZATION
//====================================================================
void OnDeinit(const int reason)
{
   Print("🛑 VolariX DLL Expert stopped.");
   PrintFormat("   Last processed bar: %s", TimeToString(last_bar_time, TIME_DATE|TIME_MINUTES));

   // Close log file
   if(log_handle != INVALID_HANDLE)
   {
      FileClose(log_handle);
      Print("📝 Execution log file closed.");
   }
}


//====================================================================
//  NOTES: This EA now uses the advanced version with real OHLCV data
//  The simple mock data version has been disabled.
//====================================================================
