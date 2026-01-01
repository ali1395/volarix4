"""
Create confidence rejection fixture from real MT5 data.
Based on log entry at line 6885: Confidence Filter: FAILED - Score 0.590 below threshold 0.6
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extract_bars_from_mt5 import extract_bars_for_fixture
import json
import MetaTrader5 as mt5

# Real case from logs
# Decision bar time: 1736478000 (2025-01-10 03:00:00)
# Confidence: 0.590 (below 0.6 threshold)
# Signal direction: BUY (but rejected due to low confidence)
# Level: 1.02867

decision_bar_time = 1736478000  # 2025-01-10 03:00:00

print("Creating confidence rejection fixture...")

try:
    bars = extract_bars_for_fixture(
        symbol="EURUSD",
        timeframe="H1",
        decision_bar_time=decision_bar_time,
        lookback_bars=200
    )

    fixture = {
        "description": "Confidence rejection - Score 0.590 below threshold 0.60",
        "source": "Real API log from volarix4_2025-12-29.log line 6885",
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
            "confidence": 0.590,  # Real value from logs
            "entry": None,
            "level_price": 1.02867,  # Real value from logs
            "sl_pips": None,
            "tp1_distance_pips": None,
            "total_cost_pips": None,
            "edge_after_costs_pips": None,
            "filters_passed": {
                "session": True,
                "trend": True,  # Assume passed (not logged as failing)
                "sr_detection": True,
                "broken_level": True,
                "rejection": True,  # Rejection was found
                "confidence": False  # FAILED here
            },
            "rejection_reason": "Confidence below threshold (0.590 < 0.60)"
        },
        "notes": [
            "Real case from production API logs (2025-12-29)",
            "Decision bar at 03:00 EST = London session (session passed)",
            "S/R levels detected (12 levels, 3 filtered as broken)",
            "Rejection pattern found: BUY at 1.02994 (Level: 1.02867)",
            "Confidence score: 0.590 < 0.60 threshold",
            "Confidence filter rejected the signal",
            "All filters before confidence passed (session, trend, S/R, broken level, rejection)"
        ]
    }

    output_path = os.path.join(
        os.path.dirname(__file__),
        "fixtures",
        "parity",
        "real_confidence_rejection_2025_01_10_low_score.json"
    )

    with open(output_path, 'w') as f:
        json.dump(fixture, f, indent=2)

    print(f"[OK] Created fixture: {output_path}")
    print(f"  Bar count: {len(bars)}")
    print(f"  Decision bar time: {decision_bar_time}")
    print(f"  Decision bar close: {bars[-1]['close']:.5f}")
    print(f"  Confidence: 0.590 (below 0.60 threshold)")

except Exception as e:
    print(f"[ERROR] Error creating confidence rejection fixture: {e}")
    raise
finally:
    mt5.shutdown()
