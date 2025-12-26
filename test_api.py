"""Test suite for Volarix 4 API"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, Any

API_URL = "http://localhost:8000"


def test_health_endpoint():
    """Test /health endpoint."""
    print("\n[TEST 1] Health Check Endpoint")
    print("-" * 60)

    response = requests.get(f"{API_URL}/health")
    assert response.status_code == 200, "Health check failed"

    data = response.json()
    assert "status" in data, "Missing 'status' field"
    assert "version" in data, "Missing 'version' field"

    print(f"  Status: {data['status']}")
    print(f"  Version: {data['version']}")
    print(f"  MT5 Connected: {data.get('mt5_connected', 'N/A')}")
    print("✓ Health check passed")


def test_root_endpoint():
    """Test root / endpoint."""
    print("\n[TEST 2] Root Endpoint")
    print("-" * 60)

    response = requests.get(f"{API_URL}/")
    assert response.status_code == 200, "Root endpoint failed"

    data = response.json()
    assert "name" in data, "Missing 'name' field"
    assert data["name"] == "Volarix 4", "Incorrect API name"

    print(f"  API Name: {data['name']}")
    print(f"  Version: {data.get('version')}")
    print(f"  Status: {data.get('status')}")
    print("✓ Root endpoint passed")


def test_signal_endpoint_valid():
    """Test /signal with valid request."""
    print("\n[TEST 3] Signal Endpoint - Valid Request")
    print("-" * 60)

    payload = {
        "symbol": "EURUSD",
        "timeframe": "H1",
        "bars": 50
    }

    print(f"  Request: {payload}")

    start_time = time.time()
    response = requests.post(f"{API_URL}/signal", json=payload)
    duration = (time.time() - start_time) * 1000

    assert response.status_code == 200, "Signal endpoint failed"

    data = response.json()

    # Verify response structure
    assert "signal" in data, "Missing 'signal' field"
    assert "confidence" in data, "Missing 'confidence' field"
    assert data["signal"] in ["BUY", "SELL", "HOLD"], f"Invalid signal: {data['signal']}"

    print(f"\n  Response:")
    print(f"    Signal: {data['signal']}")
    print(f"    Confidence: {data['confidence']:.2f}")
    print(f"    Entry: {data.get('entry', 0):.5f}")
    print(f"    SL: {data.get('sl', 0):.5f}")
    print(f"    TP1: {data.get('tp1', 0):.5f}")
    print(f"    Reason: {data['reason']}")
    print(f"\n  Response Time: {duration:.1f}ms")
    print("✓ Valid signal request passed")

    return data


def test_signal_endpoint_invalid():
    """Test /signal with invalid symbol."""
    print("\n[TEST 4] Signal Endpoint - Invalid Symbol")
    print("-" * 60)

    payload = {
        "symbol": "INVALID",
        "timeframe": "H1",
        "bars": 50
    }

    print(f"  Request: {payload}")

    response = requests.post(f"{API_URL}/signal", json=payload)
    data = response.json()

    # Should return HOLD with error reason
    assert data["signal"] == "HOLD", "Invalid symbol should return HOLD"
    print(f"\n  Response:")
    print(f"    Signal: {data['signal']}")
    print(f"    Reason: {data['reason']}")
    print("✓ Invalid request handled correctly")


def test_response_format_compatibility():
    """Verify response matches Volarix 3 format exactly."""
    print("\n[TEST 5] Volarix 3 Compatibility Check")
    print("-" * 60)

    payload = {"symbol": "EURUSD", "timeframe": "H1", "bars": 50}
    response = requests.post(f"{API_URL}/signal", json=payload)
    data = response.json()

    # Check all required fields
    required_fields = [
        "signal", "confidence", "entry", "sl",
        "tp1", "tp2", "tp3", "tp1_percent",
        "tp2_percent", "tp3_percent", "reason"
    ]

    missing_fields = []
    for field in required_fields:
        if field not in data:
            missing_fields.append(field)

    assert len(missing_fields) == 0, f"Missing fields: {missing_fields}"

    # Verify field types
    assert isinstance(data["signal"], str), "Signal must be string"
    assert isinstance(data["confidence"], (int, float)), "Confidence must be numeric"
    assert isinstance(data["entry"], (int, float)), "Entry must be numeric"
    assert isinstance(data["reason"], str), "Reason must be string"

    # Verify TP percentages sum to 1.0
    tp_sum = data["tp1_percent"] + data["tp2_percent"] + data["tp3_percent"]
    assert abs(tp_sum - 1.0) < 0.01, f"TP percentages must sum to 1.0, got {tp_sum}"

    print("  Required Fields Check:")
    for field in required_fields:
        print(f"    ✓ {field}: {type(data[field]).__name__}")

    print(f"\n  TP Percentages: {data['tp1_percent']} + {data['tp2_percent']} + {data['tp3_percent']} = {tp_sum}")
    print("✓ Response format compatible with Volarix 3")


def test_multiple_symbols():
    """Test API with different symbols."""
    print("\n[TEST 6] Multiple Symbols Test")
    print("-" * 60)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    results = []

    for symbol in symbols:
        payload = {"symbol": symbol, "timeframe": "H1", "bars": 50}

        try:
            response = requests.post(f"{API_URL}/signal", json=payload, timeout=10)
            data = response.json()
            signal = data['signal']
            confidence = data.get('confidence', 0)
            results.append((symbol, signal, confidence, "✓"))
            print(f"  {symbol:8s} → {signal:4s} (conf: {confidence:.2f}) ✓")

        except Exception as e:
            results.append((symbol, "ERROR", 0, "✗"))
            print(f"  {symbol:8s} → ERROR: {str(e)[:30]}")

    successful = len([r for r in results if r[3] == "✓"])
    print(f"\n  Successful: {successful}/{len(symbols)}")
    print("✓ Multiple symbols test completed")


def test_response_times():
    """Test API response times."""
    print("\n[TEST 7] Response Time Performance")
    print("-" * 60)

    payload = {"symbol": "EURUSD", "timeframe": "H1", "bars": 50}
    times = []

    print("  Running 5 consecutive requests...")

    for i in range(5):
        start = time.time()
        response = requests.post(f"{API_URL}/signal", json=payload, timeout=30)
        duration = (time.time() - start) * 1000
        times.append(duration)
        print(f"    Request {i+1}: {duration:.1f}ms")

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    print(f"\n  Average: {avg_time:.1f}ms")
    print(f"  Min/Max: {min_time:.1f}ms / {max_time:.1f}ms")

    assert avg_time < 5000, f"Average response time too slow: {avg_time:.1f}ms"

    print("✓ Response time performance acceptable")


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("VOLARIX 4 API TEST SUITE")
    print("=" * 70)
    print(f"API URL: {API_URL}")
    print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    tests_passed = 0
    tests_failed = 0

    tests = [
        ("Health Endpoint", test_health_endpoint),
        ("Root Endpoint", test_root_endpoint),
        ("Valid Signal Request", test_signal_endpoint_valid),
        ("Invalid Symbol Handling", test_signal_endpoint_invalid),
        ("Volarix 3 Compatibility", test_response_format_compatibility),
        ("Multiple Symbols", test_multiple_symbols),
        ("Response Time Performance", test_response_times),
    ]

    for test_name, test_func in tests:
        try:
            test_func()
            tests_passed += 1
        except AssertionError as e:
            tests_failed += 1
            print(f"\n✗ Test failed: {test_name}")
            print(f"  Error: {e}")
        except requests.exceptions.ConnectionError:
            tests_failed += 1
            print(f"\n✗ Connection Error: {test_name}")
            print(f"  Make sure the API is running: python start.py")
            break
        except Exception as e:
            tests_failed += 1
            print(f"\n✗ Unexpected error in {test_name}: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests Passed: {tests_passed}")
    print(f"Tests Failed: {tests_failed}")
    print(f"Total Tests: {len(tests)}")

    if tests_failed == 0:
        print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")
    else:
        print(f"\n✗✗✗ {tests_failed} TESTS FAILED ✗✗✗")

    print("=" * 70 + "\n")

    return tests_failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
