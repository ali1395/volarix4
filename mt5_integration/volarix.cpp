#include "pch.h"   // only if your project uses precompiled headers
#include <windows.h>
#include <wininet.h>
#include <string>
#include <sstream>
#include <comutil.h>

#pragma comment(lib, "wininet.lib")
#pragma comment(lib, "comsuppw.lib")

// ============================================================================
//  VolariXBridge.dll
//  Sends POST /signal request to FastAPI server and returns JSON response.
//  Now includes start_time and end_time for historical backtesting support.
// ============================================================================

extern "C" __declspec(dllexport)
BSTR __stdcall GetVolariXSignal(const wchar_t* symbol, const wchar_t* startTime, const wchar_t* endTime)
{
    // Convert input wide strings (from MQL5) to std::string
    // Use wcslen to get actual string length from null-terminated string
    std::wstring ws_symbol(symbol);
    std::string sym(ws_symbol.begin(), ws_symbol.end());

    std::wstring ws_start(startTime);
    std::string start_time(ws_start.begin(), ws_start.end());

    std::wstring ws_end(endTime);
    std::string end_time(ws_end.begin(), ws_end.end());

    // DEBUG: Write to a log file to see what we're receiving
    FILE* log_file = nullptr;
    fopen_s(&log_file, "E:\\VolariXBridge_Debug.txt", "a");
    if (log_file) {
        fprintf(log_file, "=== DLL Called ===\n");
        fprintf(log_file, "Symbol received (length=%d): %s\n", (int)sym.length(), sym.c_str());
        fprintf(log_file, "Start time: %s\n", start_time.c_str());
        fprintf(log_file, "End time: %s\n", end_time.c_str());
        fclose(log_file);
    }

    // ------------------------------------------------------------------------
    // Build realistic OHLCV data (50 bars)
    // In production, you would get this data from MT5 history
    // ------------------------------------------------------------------------
    std::stringstream bars;
    bars << "[";
    for (int i = 0; i < 50; ++i)
    {
        double open = 100.0 + i * 0.1;
        double high = open + 0.5;
        double low = open - 0.3;
        double close = open + 0.2;
        int volume = 10000 + i * 100;

        // Use the provided time range to generate timestamps
        // In production, use actual bar timestamps from MT5
        bars << "{\"timestamp\":\"" << start_time << "\","
            << "\"open\":" << open << ","
            << "\"high\":" << high << ","
            << "\"low\":" << low << ","
            << "\"close\":" << close << ","
            << "\"volume\":" << volume << "}";

        if (i < 49) bars << ",";
    }
    bars << "]";

    // ------------------------------------------------------------------------
    // Build JSON payload with start_time and end_time
    // ------------------------------------------------------------------------
    std::string payload =
        "{\"symbol\":\"" + sym + "\","
        "\"timeframe\":\"1h\","
        "\"data\":" + bars.str() + ","
        "\"start_time\":\"" + start_time + "\","
        "\"end_time\":\"" + end_time + "\","
        "\"model_type\":\"transformer\"}";

    // DEBUG: Log the payload being sent
    log_file = nullptr;
    fopen_s(&log_file, "E:\\VolariXBridge_Debug.txt", "a");
    if (log_file) {
        fprintf(log_file, "Payload symbol field: \"%s\"\n", sym.c_str());
        fprintf(log_file, "Payload length: %d bytes\n", (int)payload.length());
        // Log first 500 chars of payload to see symbol in JSON
        std::string preview = payload.substr(0, 500);
        fprintf(log_file, "Payload preview: %s...\n", preview.c_str());
        fprintf(log_file, "==================\n\n");
        fclose(log_file);
    }

    // ------------------------------------------------------------------------
    // Open internet session
    // ------------------------------------------------------------------------
    HINTERNET hInternet = InternetOpenA("VolariXBridge",
        INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);
    if (!hInternet)
        return SysAllocString(L"{\"error\":\"InternetOpen failed\"}");

    // Connect to local FastAPI server
    HINTERNET hConnect = InternetConnectA(hInternet,
        "127.0.0.1", 8000,
        NULL, NULL, INTERNET_SERVICE_HTTP, 0, 0);
    if (!hConnect)
    {
        InternetCloseHandle(hInternet);
        return SysAllocString(L"{\"error\":\"InternetConnect failed\"}");
    }

    // Create POST request
    const char* accept[2] = { "*/*", NULL };
    HINTERNET hRequest = HttpOpenRequestA(
        hConnect, "POST", "/signal", "HTTP/1.1", NULL, accept,
        INTERNET_FLAG_RELOAD | INTERNET_FLAG_DONT_CACHE, 0);

    if (!hRequest)
    {
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);
        return SysAllocString(L"{\"error\":\"HttpOpenRequest failed\"}");
    }

    // ------------------------------------------------------------------------
    // Set headers & send JSON body
    // ------------------------------------------------------------------------
    std::string headers =
        "Content-Type: application/json\r\n"
        "Accept: application/json\r\n";

    BOOL sent = HttpSendRequestA(
        hRequest,
        headers.c_str(),
        (DWORD)headers.length(),
        (LPVOID)payload.c_str(),
        (DWORD)payload.length()
    );

    if (!sent)
    {
        InternetCloseHandle(hRequest);
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);
        return SysAllocString(L"{\"error\":\"HttpSendRequest failed\"}");
    }

    // ------------------------------------------------------------------------
    // Read response
    // ------------------------------------------------------------------------
    char buffer[4096];
    DWORD bytesRead;
    std::stringstream ss;

    while (InternetReadFile(hRequest, buffer, sizeof(buffer) - 1, &bytesRead) && bytesRead > 0)
    {
        buffer[bytesRead] = 0;
        ss << buffer;
    }

    InternetCloseHandle(hRequest);
    InternetCloseHandle(hConnect);
    InternetCloseHandle(hInternet);

    // ------------------------------------------------------------------------
    // Return JSON response as BSTR (Unicode string for MQL5)
    // ------------------------------------------------------------------------
    std::string result = ss.str();
    std::wstring wresult(result.begin(), result.end());
    return SysAllocString(wresult.c_str());
}


// ============================================================================
//  Alternative version: GetVolariXSignalWithBars
//  Accepts actual OHLCV data from MQL5 instead of generating mock data
// ============================================================================

struct OHLCVBar {
    char timestamp[32];
    double open;
    double high;
    double low;
    double close;
    double volume;
};

extern "C" __declspec(dllexport)
BSTR __stdcall GetVolariXSignalWithBars(
    const wchar_t* symbol,
    const wchar_t* timeframe,         // Backward compat field
    OHLCVBar* bars,
    int barCount,
    const wchar_t* startTime,
    const wchar_t* endTime,
    const wchar_t* executionTimeframe,  // NEW: Explicit execution timeframe
    const wchar_t* contextTimeframe,    // NEW: Context timeframe (empty = single-TF)
    OHLCVBar* contextBars,              // NEW: Context bars (can be NULL)
    int contextBarCount)                // NEW: Context bar count (0 = single-TF)
{
    // Convert input wide strings (from MQL5) to std::string
    std::wstring ws_symbol(symbol);
    std::string sym(ws_symbol.begin(), ws_symbol.end());

    std::wstring ws_timeframe(timeframe);
    std::string tf(ws_timeframe.begin(), ws_timeframe.end());

    std::wstring ws_start(startTime);
    std::string start_time(ws_start.begin(), ws_start.end());

    std::wstring ws_end(endTime);
    std::string end_time(ws_end.begin(), ws_end.end());

    // NEW: Convert multi-TF parameters
    std::wstring ws_exec_tf(executionTimeframe);
    std::string exec_tf(ws_exec_tf.begin(), ws_exec_tf.end());

    std::wstring ws_ctx_tf(contextTimeframe);
    std::string ctx_tf(ws_ctx_tf.begin(), ws_ctx_tf.end());

    // Determine if multi-TF mode is enabled
    bool isMultiTF = (!ctx_tf.empty() && contextBarCount > 0);

    // DEBUG: Log what we received
    FILE* log_file = nullptr;
    fopen_s(&log_file, "E:\\VolariXBridge_Debug.txt", "a");
    if (log_file) {
        fprintf(log_file, "=== GetVolariXSignalWithBars Called (v3.2 - Multi-TF) ===\n");
        fprintf(log_file, "Symbol: %s (length=%d)\n", sym.c_str(), (int)sym.length());
        fprintf(log_file, "Execution TF: '%s' (length=%d)\n", exec_tf.c_str(), (int)exec_tf.length());
        fprintf(log_file, "Context TF: '%s' (length=%d)\n", ctx_tf.c_str(), (int)ctx_tf.length());
        fprintf(log_file, "Execution bar count: %d\n", barCount);
        fprintf(log_file, "Context bar count: %d\n", contextBarCount);
        fprintf(log_file, "Multi-TF mode: %s\n", isMultiTF ? "ENABLED" : "DISABLED");
        fprintf(log_file, "Start time: %s\n", start_time.c_str());
        fprintf(log_file, "End time: %s\n", end_time.c_str());
        fprintf(log_file, "==================\n\n");
        fclose(log_file);
    }

    // ------------------------------------------------------------------------
    // Build OHLCV data from actual MT5 bars (execution timeframe)
    // ------------------------------------------------------------------------
    std::stringstream bars_json;
    bars_json << "[";
    for (int i = 0; i < barCount; ++i)
    {
        bars_json << "{\"timestamp\":\"" << bars[i].timestamp << "\","
            << "\"open\":" << bars[i].open << ","
            << "\"high\":" << bars[i].high << ","
            << "\"low\":" << bars[i].low << ","
            << "\"close\":" << bars[i].close << ","
            << "\"volume\":" << bars[i].volume << "}";

        if (i < barCount - 1) bars_json << ",";
    }
    bars_json << "]";

    // ------------------------------------------------------------------------
    // Build context OHLCV data if multi-TF mode
    // ------------------------------------------------------------------------
    std::stringstream ctx_bars_json;
    if (isMultiTF && contextBars != nullptr && contextBarCount > 0)
    {
        ctx_bars_json << "[";
        for (int i = 0; i < contextBarCount; ++i)
        {
            ctx_bars_json << "{\"timestamp\":\"" << contextBars[i].timestamp << "\","
                << "\"open\":" << contextBars[i].open << ","
                << "\"high\":" << contextBars[i].high << ","
                << "\"low\":" << contextBars[i].low << ","
                << "\"close\":" << contextBars[i].close << ","
                << "\"volume\":" << contextBars[i].volume << "}";

            if (i < contextBarCount - 1) ctx_bars_json << ",";
        }
        ctx_bars_json << "]";
    }

    // ------------------------------------------------------------------------
    // Build JSON payload with multi-TF support
    // ------------------------------------------------------------------------
    std::stringstream payload_stream;
    payload_stream << "{\"symbol\":\"" << sym << "\","
        << "\"timeframe\":\"" << exec_tf << "\","  // Backward compat
        << "\"execution_timeframe\":\"" << exec_tf << "\","  // NEW: Explicit execution TF
        << "\"data\":" << bars_json.str() << ","
        << "\"start_time\":\"" << start_time << "\","
        << "\"end_time\":\"" << end_time << "\","
        << "\"model_type\":\"statistical\"";  // Changed default to statistical

    // Add multi-TF fields if enabled
    if (isMultiTF)
    {
        payload_stream << ",\"context_timeframe\":\"" << ctx_tf << "\""
            << ",\"context_data\":" << ctx_bars_json.str();
    }

    payload_stream << "}";
    std::string payload = payload_stream.str();

    // DEBUG: Log payload preview
    log_file = nullptr;
    fopen_s(&log_file, "E:\\VolariXBridge_Debug.txt", "a");
    if (log_file) {
        fprintf(log_file, "Payload length: %d bytes\n", (int)payload.length());
        // Log first 1000 chars of payload to verify multi-TF fields
        std::string preview = payload.length() > 1000 ? payload.substr(0, 1000) + "..." : payload;
        fprintf(log_file, "Payload preview: %s\n", preview.c_str());
        fprintf(log_file, "==================\n\n");
        fclose(log_file);
    }

    // ------------------------------------------------------------------------
    // Open internet session
    // ------------------------------------------------------------------------
    HINTERNET hInternet = InternetOpenA("VolariXBridge",
        INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);
    if (!hInternet)
        return SysAllocString(L"{\"error\":\"InternetOpen failed\"}");

    // Connect to local FastAPI server
    HINTERNET hConnect = InternetConnectA(hInternet,
        "127.0.0.1", 8000,
        NULL, NULL, INTERNET_SERVICE_HTTP, 0, 0);
    if (!hConnect)
    {
        InternetCloseHandle(hInternet);
        return SysAllocString(L"{\"error\":\"InternetConnect failed\"}");
    }

    // Create POST request
    const char* accept[2] = { "*/*", NULL };
    HINTERNET hRequest = HttpOpenRequestA(
        hConnect, "POST", "/signal", "HTTP/1.1", NULL, accept,
        INTERNET_FLAG_RELOAD | INTERNET_FLAG_DONT_CACHE, 0);

    if (!hRequest)
    {
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);
        return SysAllocString(L"{\"error\":\"HttpOpenRequest failed\"}");
    }

    // Set headers & send JSON body
    std::string headers =
        "Content-Type: application/json\r\n"
        "Accept: application/json\r\n";

    BOOL sent = HttpSendRequestA(
        hRequest,
        headers.c_str(),
        (DWORD)headers.length(),
        (LPVOID)payload.c_str(),
        (DWORD)payload.length()
    );

    if (!sent)
    {
        InternetCloseHandle(hRequest);
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);
        return SysAllocString(L"{\"error\":\"HttpSendRequest failed\"}");
    }

    // Read response
    char buffer[4096];
    DWORD bytesRead;
    std::stringstream ss;

    while (InternetReadFile(hRequest, buffer, sizeof(buffer) - 1, &bytesRead) && bytesRead > 0)
    {
        buffer[bytesRead] = 0;
        ss << buffer;
    }

    InternetCloseHandle(hRequest);
    InternetCloseHandle(hConnect);
    InternetCloseHandle(hInternet);

    // Return JSON response
    std::string result = ss.str();
    std::wstring wresult(result.begin(), result.end());
    return SysAllocString(wresult.c_str());
}
