"""Volarix 4 Configuration"""

import os
from typing import Dict, Tuple
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# MT5 Connection (from environment variables)
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

# S/R Level Detection
SR_CONFIG = {
    "lookback": 80,              # DECREASE from 200 to 80 ⚠️ CRITICAL
    "swing_window": 5,           # Keep
    "min_touches": 3,            # Keep
    "cluster_pips": 10.0,        # Keep
    "min_level_score": 60.0      # Keep
}


# Rejection Candle Criteria
REJECTION_CONFIG = {
    "min_wick_body_ratio": 1.5,  # Keep
    "max_distance_pips": 10.0,   # Keep
    "close_position_buy": 0.60,  # Keep
    "close_position_sell": 0.40, # Keep
    "lookback_candles": 5,       # Keep
    "min_confidence": 0.60       # DEFAULT: 0.60 (best backtest parity) - overridable via API
}


# Risk Management
RISK_CONFIG = {
    "sl_pips_beyond": 10.0,      # Keep this
    "max_sl_pips": 25.0,         # Increase from 20 to 25 (more flexibility)
    "min_rr": 1.5,               # DECREASE from 2.0 to 1.5 ⚠️ CRITICAL
    "tp1_r": 1.0,                # Keep
    "tp2_r": 2.0,                # Keep
    "tp3_r": 3.0,                # Keep
    "tp1_percent": 0.50,         # Change from 0.40 to 0.50 (take more profit early)
    "tp2_percent": 0.30,         # Change from 0.40 to 0.30
    "tp3_percent": 0.20          # Keep at 0.20
}


# Backtest Parity Defaults (matches best run from tests/backtest.py)
# These are defaults when MT5 EA doesn't specify - can be overridden per request
BACKTEST_PARITY_CONFIG = {
    "min_confidence": 0.60,                    # Best backtest param
    "broken_level_cooldown_hours": 48.0,       # Best backtest param (was 24h)
    "broken_level_break_pips": 15.0,           # Default break threshold
    "min_edge_pips": 4.0,                      # Minimum profitable edge after costs

    # Cost model defaults (typical broker costs)
    "spread_pips": 1.0,                        # Typical EURUSD spread
    "slippage_pips": 0.5,                      # One-way slippage estimate
    "commission_per_side_per_lot": 7.0,        # USD per lot per side
    "usd_per_pip_per_lot": 10.0,               # Standard forex lot
    "lot_size": 1.0                            # Default lot size for commission calc
}


# Session Times (EST hours)
SESSIONS: Dict[str, Tuple[int, int]] = {
    "london": (3, 11),    # 3am - 11am EST
    "ny": (8, 22)         # 8am - 10pm EST (extended to cover full NY session)
}

# API Settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Legacy CONFIG dict for backward compatibility
CONFIG = {
    "mt5_login": MT5_LOGIN,
    "mt5_password": MT5_PASSWORD,
    "mt5_server": MT5_SERVER,
    "sessions": SESSIONS,
    "sr_lookback": SR_CONFIG["lookback"],
    "min_touches": SR_CONFIG["min_touches"],
    "touch_threshold_pips": SR_CONFIG["cluster_pips"],
    "wick_body_ratio": REJECTION_CONFIG["min_wick_body_ratio"],
    "close_zone_percent": REJECTION_CONFIG["close_position_buy"] - 0.5,
    "sl_pips_beyond": RISK_CONFIG["sl_pips_beyond"],
    "tp_ratios": [RISK_CONFIG["tp1_r"], RISK_CONFIG["tp2_r"], RISK_CONFIG["tp3_r"]],
    "tp_percents": [RISK_CONFIG["tp1_percent"], RISK_CONFIG["tp2_percent"], RISK_CONFIG["tp3_percent"]],
}
