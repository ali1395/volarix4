"""
Extract bar windows from MT5 for parity test fixtures.

This script connects to MT5 and extracts the exact bar windows that were
used in the logged API calls, then saves them as JSON fixtures.
"""

import sys
import os
import json
from datetime import datetime
from typing import List, Dict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import MetaTrader5 as mt5
import pandas as pd
from volarix4.core.data import connect_mt5, fetch_ohlc


def extract_bars_for_fixture(
    symbol: str,
    timeframe: str,
    decision_bar_time: int,
    lookback_bars: int = 200
) -> List[Dict]:
    """
    Extract bars from MT5 for a specific decision bar time.

    Args:
        symbol: Trading symbol (e.g., "EURUSD")
        timeframe: Timeframe (e.g., "H1")
        decision_bar_time: Unix timestamp of the decision bar (last bar)
        lookback_bars: Number of bars to include (default: 200)

    Returns:
        List of bar dicts with {time, open, high, low, close, volume}
    """
    # Connect to MT5
    if not connect_mt5():
        raise RuntimeError("Failed to connect to MT5")

    # Map timeframe string to MT5 constant
    timeframe_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
    }

    if timeframe not in timeframe_map:
        raise ValueError(f"Invalid timeframe: {timeframe}")

    tf_mt5 = timeframe_map[timeframe]

    # Fetch bars ending at decision_bar_time
    rates = mt5.copy_rates_from(symbol, tf_mt5, decision_bar_time, lookback_bars)

    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No data returned from MT5 for {symbol} {timeframe}")

    # Convert to list of dicts
    bars = []
    for rate in rates:
        bars.append({
            "time": int(rate['time']),
            "open": float(rate['open']),
            "high": float(rate['high']),
            "low": float(rate['low']),
            "close": float(rate['close']),
            "volume": int(rate['tick_volume'])
        })

    return bars


def create_session_rejection_fixture():
    """
    Create fixture for session rejection case.
    Based on log line: Session Check: INVALID - Outside London/NY hours (2025-01-02 00:00:00)
    Decision bar time: 1735776000 (2025-01-02 00:00:00)
    """
    print("Creating session rejection fixture...")

    decision_bar_time = 1735776000  # 2025-01-02 00:00:00 (midnight - outside session)

    try:
        bars = extract_bars_for_fixture(
            symbol="EURUSD",
            timeframe="H1",
            decision_bar_time=decision_bar_time,
            lookback_bars=200
        )

        fixture = {
            "description": "Session rejection - Decision bar at 00:00 EST (outside London/NY hours)",
            "source": "Real API log from volarix4_2025-12-29.log line 33",
            "symbol": "EURUSD",
            "timeframe": "H1",
            "parameters": {
                "min_confidence": 0.60,
                "broken_level_cooldown_hours": 48.0,
                "broken_level_break_pips": 15.0,
                "min_edge_pips": 4.0,
                "spread_pips": 1.0,
                "slippage_pips": 0.5,
                "commission_per_side_per_lot": 7.0,
                "usd_per_pip_per_lot": 10.0,
                "lot_size": 1.0,
                "enable_session_filter": True,
                "enable_trend_filter": True,
                "enable_signal_cooldown": False,
                "enable_confidence_filter": True,
                "enable_broken_level_filter": True
            },
            "bars": bars,
            "expected_results": {
                "decision_bar_index": len(bars) - 1,
                "decision_bar_time": decision_bar_time,
                "decision_bar_close": bars[-1]['close'],
                "signal": "HOLD",
                "confidence": None,
                "entry": None,
                "level_price": None,
                "sl_pips": None,
                "tp1_distance_pips": None,
                "total_cost_pips": None,
                "edge_after_costs_pips": None,
                "filters_passed": {
                    "session": False
                },
                "rejection_reason": "Outside trading session (London/NY only)"
            },
            "notes": [
                "Real case from production API logs (2025-12-29)",
                "Decision bar at 00:00 EST = midnight (Asian hours)",
                "London session: 03:00-11:00 EST, NY session: 08:00-22:00 EST",
                "00:00 EST is outside both sessions",
                "Session filter should reject immediately before other filters run"
            ]
        }

        # Save fixture
        output_path = os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "parity",
            "real_session_rejection_2025_01_02_midnight.json"
        )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(fixture, f, indent=2)

        print(f"[OK] Created fixture: {output_path}")
        print(f"  Bar count: {len(bars)}")
        print(f"  First bar: {datetime.fromtimestamp(bars[0]['time'])}")
        print(f"  Last bar: {datetime.fromtimestamp(bars[-1]['time'])}")
        print(f"  Decision bar close: {bars[-1]['close']:.5f}")

    except Exception as e:
        print(f"[ERROR] Error creating session rejection fixture: {e}")
        raise


def create_trade_accepted_fixture():
    """
    Create fixture for trade accepted case.
    Based on log line: *** ALL FILTERS PASSED - TRADE SIGNAL GENERATED ***
    Decision bar time: 1735786800 (2025-01-02 03:00:00)
    """
    print("\nCreating trade accepted fixture...")

    decision_bar_time = 1735786800  # 2025-01-02 03:00:00 (London session start)

    try:
        bars = extract_bars_for_fixture(
            symbol="EURUSD",
            timeframe="H1",
            decision_bar_time=decision_bar_time,
            lookback_bars=200
        )

        # Note: We'll need to run the actual logic to determine signal details
        # For now, create a placeholder that needs to be filled
        fixture = {
            "description": "Trade accepted - All filters passed at 03:00 EST (London session start)",
            "source": "Real API log from volarix4_2025-12-29.log line 177",
            "symbol": "EURUSD",
            "timeframe": "H1",
            "parameters": {
                "min_confidence": 0.60,
                "broken_level_cooldown_hours": 48.0,
                "broken_level_break_pips": 15.0,
                "min_edge_pips": 4.0,
                "spread_pips": 1.0,
                "slippage_pips": 0.5,
                "commission_per_side_per_lot": 7.0,
                "usd_per_pip_per_lot": 10.0,
                "lot_size": 1.0,
                "enable_session_filter": True,
                "enable_trend_filter": True,
                "enable_signal_cooldown": False,
                "enable_confidence_filter": True,
                "enable_broken_level_filter": True
            },
            "bars": bars,
            "expected_results": {
                "decision_bar_index": len(bars) - 1,
                "decision_bar_time": decision_bar_time,
                "decision_bar_close": bars[-1]['close'],
                "signal": "BUY_OR_SELL",  # To be determined by running logic
                "confidence": None,  # To be filled
                "entry": None,  # To be filled
                "level_price": None,  # To be filled
                "sl_pips": None,  # To be filled
                "tp1_distance_pips": None,  # To be filled
                "total_cost_pips": 3.4,  # Fixed based on cost model
                "edge_after_costs_pips": None,  # To be filled
                "filters_passed": {
                    "session": True,
                    "trend": True,
                    "sr_detection": True,
                    "broken_level": True,
                    "rejection": True,
                    "confidence": True,
                    "trend_alignment": True,
                    "signal_cooldown": True,
                    "min_edge": True
                },
                "rejection_reason": None
            },
            "notes": [
                "Real case from production API logs (2025-12-29)",
                "Decision bar at 03:00 EST = London session start",
                "All filters passed - trade signal generated",
                "IMPORTANT: Signal details (BUY/SELL, confidence, etc.) need to be filled",
                "by running the actual API logic on these bars"
            ]
        }

        # Save fixture
        output_path = os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "parity",
            "real_trade_accepted_2025_01_02_london_open.json"
        )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(fixture, f, indent=2)

        print(f"[OK] Created fixture: {output_path}")
        print(f"  Bar count: {len(bars)}")
        print(f"  First bar: {datetime.fromtimestamp(bars[0]['time'])}")
        print(f"  Last bar: {datetime.fromtimestamp(bars[-1]['time'])}")
        print(f"  Decision bar close: {bars[-1]['close']:.5f}")
        print("\n  NOTE: This fixture needs signal details filled by running API logic")

    except Exception as e:
        print(f"[ERROR] Error creating trade accepted fixture: {e}")
        raise


if __name__ == "__main__":
    print("=" * 70)
    print("MT5 Bar Extraction for Parity Test Fixtures")
    print("=" * 70)

    try:
        # Create session rejection fixture
        create_session_rejection_fixture()

        # Create trade accepted fixture
        create_trade_accepted_fixture()

        print("\n" + "=" * 70)
        print("[OK] Fixtures created successfully!")
        print("=" * 70)
        print("\nNext steps:")
        print("1. Review the fixtures in tests/fixtures/parity/")
        print("2. For trade_accepted fixture, run API logic to fill signal details")
        print("3. Update test_backtest_api_parity.py to use these fixtures")

    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        sys.exit(1)
    finally:
        # Shutdown MT5
        mt5.shutdown()
