"""
Core trading logic modules.

This package contains the core components of the Volarix 4 trading strategy:
- data: MT5 data fetching and session validation
- sr_levels: Support/Resistance level detection
- rejection: Rejection candle pattern recognition
- trade_setup: SL/TP calculation and trade setup
"""

from volarix4.core.data import fetch_ohlc, is_valid_session, connect_mt5
from volarix4.core.sr_levels import detect_sr_levels
from volarix4.core.rejection import find_rejection_candle
from volarix4.core.trade_setup import calculate_trade_setup

__all__ = [
    "fetch_ohlc",
    "is_valid_session",
    "connect_mt5",
    "detect_sr_levels",
    "find_rejection_candle",
    "calculate_trade_setup"
]
