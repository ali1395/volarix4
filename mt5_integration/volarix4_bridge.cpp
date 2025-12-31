//=============================================================================
//  Volarix4Bridge.dll
//  C++ DLL Bridge for MT5 -> Volarix 4 FastAPI
//
//  Sends OHLCV data to Volarix 4 API and returns JSON response
//  Single-TF only (no multi-TF complexity)
//=============================================================================

// NOTE: If your project uses precompiled headers, uncomment the next line:
// #include "pch.h"

#include <windows.h>
#include <wininet.h>
#include <string>
#include <sstream>
#include <iomanip>
#include <comutil.h>

#pragma comment(lib, "wininet.lib")
#pragma comment(lib, "comsuppw.lib")

// OHLCV Bar structure (must match MT5 definition)
// CRITICAL: MQL5 uses tight packing with NO PADDING (total: 44 bytes)
#pragma pack(push, 1)  // No padding - tight packing to match MQL5
struct OHLCVBar
{
    long long timestamp; // Unix timestamp (8 bytes) - use long long to ensure 8 bytes
    double open;         // 8 bytes
    double high;         // 8 bytes
    double low;          // 8 bytes
    double close;        // 8 bytes
    int volume;          // 4 bytes
};                       // Total: exactly 44 bytes (no padding)
#pragma pack(pop)

//=============================================================================
//  Helper: Write debug log
//=============================================================================
void WriteDebugLog(const char* message)
{
    FILE* log_file = nullptr;
    fopen_s(&log_file, "E:\\Volarix4Bridge_Debug.txt", "a");
    if (log_file) {
        fprintf(log_file, "%s\n", message);
        fclose(log_file);
    }
}

//=============================================================================
//  Main DLL Function: GetVolarix4Signal (Updated for API v4)
//=============================================================================
extern "C" __declspec(dllexport)
BSTR __stdcall GetVolarix4Signal(
    const wchar_t* symbol,
    const wchar_t* timeframe,
    OHLCVBar* bars,
    int barCount,
    const wchar_t* apiUrl,
    double minConfidence,
    double brokenLevelCooldownHours,
    double brokenLevelBreakPips,
    double minEdgePips,
    double spreadPips,
    double slippagePips,
    double commissionPerSidePerLot,
    double usdPerPipPerLot,
    double lotSize)
{
    // Debug: Log struct size to verify packing
    std::stringstream struct_debug;
    struct_debug << "=== DLL Called ===" << std::endl;
    struct_debug << "OHLCVBar struct size: " << sizeof(OHLCVBar) << " bytes (should be 44)" << std::endl;
    struct_debug << "Bar count: " << barCount << std::endl;
    if (barCount > 0) {
        struct_debug << "First bar: timestamp=" << bars[0].timestamp
                  << ", open=" << bars[0].open
                  << ", close=" << bars[0].close << std::endl;
    }
    if (barCount > 1) {
        struct_debug << "Second bar: timestamp=" << bars[1].timestamp
                  << ", open=" << bars[1].open
                  << ", close=" << bars[1].close << std::endl;
    }
    WriteDebugLog(struct_debug.str().c_str());

    // Convert wide strings to std::string
    std::wstring ws_symbol(symbol);
    std::string sym(ws_symbol.begin(), ws_symbol.end());

    std::wstring ws_tf(timeframe);
    std::string tf(ws_tf.begin(), ws_tf.end());

    // Build JSON array for OHLCV data
    std::stringstream data_array;
    data_array << "[";

    for (int i = 0; i < barCount; i++)
    {
        data_array << "{"
            << "\"time\":" << bars[i].timestamp << ","
            << "\"open\":" << std::fixed << std::setprecision(5) << bars[i].open << ","
            << "\"high\":" << std::fixed << std::setprecision(5) << bars[i].high << ","
            << "\"low\":" << std::fixed << std::setprecision(5) << bars[i].low << ","
            << "\"close\":" << std::fixed << std::setprecision(5) << bars[i].close << ","
            << "\"volume\":" << bars[i].volume
            << "}";

        if (i < barCount - 1)
            data_array << ",";
    }

    data_array << "]";

    // Build complete JSON payload (matching Volarix 4 API with new parameters)
    std::stringstream payload;
    payload << "{"
        << "\"symbol\":\"" << sym << "\","
        << "\"timeframe\":\"" << tf << "\","
        << "\"data\":" << data_array.str() << ","
        << "\"min_confidence\":" << std::fixed << std::setprecision(2) << minConfidence << ","
        << "\"broken_level_cooldown_hours\":" << std::fixed << std::setprecision(1) << brokenLevelCooldownHours << ","
        << "\"broken_level_break_pips\":" << std::fixed << std::setprecision(1) << brokenLevelBreakPips << ","
        << "\"min_edge_pips\":" << std::fixed << std::setprecision(1) << minEdgePips << ","
        << "\"spread_pips\":" << std::fixed << std::setprecision(1) << spreadPips << ","
        << "\"slippage_pips\":" << std::fixed << std::setprecision(1) << slippagePips << ","
        << "\"commission_per_side_per_lot\":" << std::fixed << std::setprecision(1) << commissionPerSidePerLot << ","
        << "\"usd_per_pip_per_lot\":" << std::fixed << std::setprecision(1) << usdPerPipPerLot << ","
        << "\"lot_size\":" << std::fixed << std::setprecision(2) << lotSize
        << "}";

    std::string payload_str = payload.str();

    // Debug log
    std::stringstream debug_msg;
    debug_msg << "=== Volarix 4 API Call ===" << std::endl;
    debug_msg << "Symbol: " << sym << std::endl;
    debug_msg << "Timeframe: " << tf << std::endl;
    debug_msg << "Bars: " << barCount << std::endl;
    debug_msg << "Payload size: " << payload_str.length() << " bytes" << std::endl;
    WriteDebugLog(debug_msg.str().c_str());

    //=========================================================================
    //  Parse API URL to extract host and port
    //=========================================================================
    std::wstring ws_apiUrl(apiUrl);
    std::string api_url_str(ws_apiUrl.begin(), ws_apiUrl.end());

    // Parse URL (expecting format: http://host:port)
    std::string host = "localhost";
    int port = 8000;

    size_t proto_end = api_url_str.find("://");
    if (proto_end != std::string::npos) {
        std::string url_part = api_url_str.substr(proto_end + 3);
        size_t port_pos = url_part.find(":");
        if (port_pos != std::string::npos) {
            host = url_part.substr(0, port_pos);
            std::string port_str = url_part.substr(port_pos + 1);
            port = std::stoi(port_str);
        } else {
            host = url_part;
        }
    }

    //=========================================================================
    //  HTTP POST to Volarix 4 API
    //=========================================================================

    // Open internet session
    HINTERNET hInternet = InternetOpenA("Volarix4Bridge",
        INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);

    if (!hInternet) {
        WriteDebugLog("ERROR: InternetOpen failed");
        return SysAllocString(L"{\"error\":\"InternetOpen failed\"}");
    }

    // Connect to server using parsed host and port
    HINTERNET hConnect = InternetConnectA(hInternet,
        host.c_str(),  // Parsed from API URL
        port,          // Parsed from API URL
        NULL, NULL, INTERNET_SERVICE_HTTP, 0, 0);

    if (!hConnect) {
        InternetCloseHandle(hInternet);
        WriteDebugLog("ERROR: InternetConnect failed");
        return SysAllocString(L"{\"error\":\"InternetConnect failed\"}");
    }

    // Open HTTP request
    LPCSTR acceptTypes[] = { "application/json", NULL };
    HINTERNET hRequest = HttpOpenRequestA(hConnect,
        "POST",
        "/signal",  // Volarix 4 endpoint
        NULL,
        NULL,
        acceptTypes,
        INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE,
        0);

    if (!hRequest) {
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);
        WriteDebugLog("ERROR: HttpOpenRequest failed");
        return SysAllocString(L"{\"error\":\"HttpOpenRequest failed\"}");
    }

    // Set headers
    std::string headers = "Content-Type: application/json\r\n";

    // Send request
    BOOL bSent = HttpSendRequestA(hRequest,
        headers.c_str(),
        (DWORD)headers.length(),
        (LPVOID)payload_str.c_str(),
        (DWORD)payload_str.length());

    if (!bSent) {
        InternetCloseHandle(hRequest);
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);

        std::stringstream err_msg;
        err_msg << "ERROR: HttpSendRequest failed. Error code: " << GetLastError();
        WriteDebugLog(err_msg.str().c_str());

        return SysAllocString(L"{\"error\":\"HttpSendRequest failed\"}");
    }

    // Read response
    std::string response;
    char buffer[4096];
    DWORD bytesRead = 0;

    while (InternetReadFile(hRequest, buffer, sizeof(buffer) - 1, &bytesRead) && bytesRead > 0)
    {
        buffer[bytesRead] = '\0';
        response += buffer;
    }

    // Cleanup
    InternetCloseHandle(hRequest);
    InternetCloseHandle(hConnect);
    InternetCloseHandle(hInternet);

    // Debug log response
    std::stringstream response_msg;
    response_msg << "API Response (" << response.length() << " bytes): "
        << response.substr(0, 200) << "..." << std::endl;
    WriteDebugLog(response_msg.str().c_str());

    // Convert response to BSTR for MQL5
    std::wstring ws_response(response.begin(), response.end());
    return SysAllocString(ws_response.c_str());
}

//=============================================================================
//  DLL Entry Point
//=============================================================================
BOOL APIENTRY DllMain(HMODULE hModule,
    DWORD  ul_reason_for_call,
    LPVOID lpReserved)
{
    switch (ul_reason_for_call)
    {
    case DLL_PROCESS_ATTACH:
        WriteDebugLog("=== Volarix4Bridge.dll loaded ===");
        break;
    case DLL_PROCESS_DETACH:
        WriteDebugLog("=== Volarix4Bridge.dll unloaded ===");
        break;
    }
    return TRUE;
}
