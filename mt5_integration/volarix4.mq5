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
//  IMPORT DLL
//====================================================================
#import "VolariXBridge.dll"
   // Send OHLCV data to Volarix 4 API and get signal
   string GetVolarix4Signal(
      string symbol,
      string timeframe,
      OHLCVBar &bars[],
      int barCount
   );
#import

//====================================================================
//  INPUT PARAMETERS
//====================================================================
input string SymbolToCheck = "EURUSD";           // Symbol to trade
input ENUM_TIMEFRAMES Timeframe = PERIOD_H1;     // Timeframe
input int    LookbackBars  = 50;                 // Number of bars to send to API
input string API_URL = "http://localhost:8000";  // Volarix 4 API URL

// Trade Management
input double RiskPercent = 1.0;                  // Risk per trade (%)
input int    MaxPositions = 1;                   // Max open positions
input bool   EnableTrading = true;               // Enable auto-trading

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
   Print("Make sure 'Allow DLL imports' is enabled");
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

   // Copy bars from MT5
   MqlRates rates[];
   int copied = CopyRates(SymbolToCheck, Timeframe, 0, LookbackBars, rates);

   if(copied <= 0)
   {
      Print("Failed to copy bars from MT5");
      return;
   }

   // Convert to OHLCVBar array
   OHLCVBar bars[];
   ArrayResize(bars, copied);

   for(int i = 0; i < copied; i++)
   {
      bars[i].timestamp = (long)rates[i].time;
      bars[i].open = rates[i].open;
      bars[i].high = rates[i].high;
      bars[i].low = rates[i].low;
      bars[i].close = rates[i].close;
      bars[i].volume = (int)rates[i].tick_volume;
   }

   // Call DLL to get signal from API
   Print("Calling DLL: GetVolarix4Signal()");
   Print("  Symbol: ", SymbolToCheck);
   Print("  Timeframe: ", TimeframeToString(Timeframe));
   Print("  Bars to send: ", copied);

   ResetLastError();
   string response = GetVolarix4Signal(
      SymbolToCheck,
      TimeframeToString(Timeframe),
      bars,
      copied
   );

   int dll_error = GetLastError();
   if(dll_error != 0)
   {
      PrintFormat("ERROR: DLL call failed with error code %d", dll_error);

      Print("  Make sure:");
      Print("    1. Volarix4Bridge.dll is in [MT5 Data Folder]\\MQL5\\Libraries\\");
      Print("    2. 'Allow DLL imports' is enabled in Tools -> Options -> Expert Advisors");
      Print("    3. The DLL was compiled for x64 architecture");
      return;
   }

   if(StringLen(response) == 0)
   {
      Print("WARNING: Empty response from API");
      Print("  Check debug log at: E:\\Volarix4Bridge_Debug.txt");
      Print("  Verify Volarix 4 API is running at: ", API_URL);
      return;
   }

   Print("DLL Response received (", StringLen(response), " bytes)");

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

   // Extract confidence (simplified)
   int conf_pos = StringFind(response, "\"confidence\":");
   if(conf_pos >= 0)
   {
      string conf_str = StringSubstr(response, conf_pos + 14, 10);
      confidence = StringToDouble(conf_str);
   }

   PrintFormat("API Response: Signal=%s, Confidence=%.2f", signal, confidence);

   // Execute trade if signal is BUY or SELL
   if(EnableTrading && (signal == "BUY" || signal == "SELL"))
   {
      // Check if we already have max positions
      if(GetOpenPositionsCount() >= MaxPositions)
      {
         Print("Max positions reached. Skipping trade.");
         return;
      }

      // Parse entry and SL (simplified - use proper JSON parser in production)
      // For now, use current price and simple SL
      double current_price = (signal == "BUY") ?
         SymbolInfoDouble(SymbolToCheck, SYMBOL_ASK) :
         SymbolInfoDouble(SymbolToCheck, SYMBOL_BID);

      // Calculate lot size
      double sl_price = current_price + (signal == "BUY" ? -0.0013 : 0.0013);
      double lot = CalculateLotSize(current_price, sl_price);

      // Open trade
      MqlTradeRequest request = {};
      MqlTradeResult result = {};

      request.action = TRADE_ACTION_DEAL;
      request.symbol = SymbolToCheck;
      request.volume = lot;
      request.type = (signal == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      request.price = current_price;
      request.sl = sl_price;
      request.deviation = 10;
      request.magic = 20241225;
      request.comment = "Volarix4 S/R";

      if(OrderSend(request, result))
      {
         PrintFormat("Trade opened: Ticket=%d, Price=%.5f, Lot=%.2f",
                     result.order, result.price, lot);

         // Log to CSV
         string log_line = StringFormat("%s,%s,%s,%.2f,%.5f,%.5f,0,0,0,%s,%d,SUCCESS",
                                        TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
                                        SymbolToCheck, signal, confidence,
                                        result.price, sl_price, reason, result.order);
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
