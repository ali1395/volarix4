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
    "lookback": 50,              # Bars to look back for swings
    "swing_window": 5,           # Window for swing detection
    "min_touches": 3,            # Min touches to qualify as S/R
    "cluster_pips": 10.0,        # Pip distance to cluster levels
    "min_level_score": 60.0      # Min score to use level
}

# Rejection Candle Criteria
REJECTION_CONFIG = {
    "min_wick_body_ratio": 1.5,  # Min wick/body ratio
    "max_distance_pips": 10.0,   # Max distance from level
    "close_position_buy": 0.60,  # Close must be in top 60% for BUY
    "close_position_sell": 0.40, # Close must be in bottom 40% for SELL
    "lookback_candles": 5,       # Number of recent candles to check
    "min_confidence": 0.70       # Minimum confidence to execute signal (lowered from 0.80)
}

# Risk Management
RISK_CONFIG = {
    "sl_pips_beyond": 10.0,      # SL distance beyond level
    "max_sl_pips": 20.0,         # Maximum SL in pips (reject trade if exceeded)
    "min_rr": 2.0,               # Minimum risk:reward ratio (was 1.5, now 2.0)
    "tp1_r": 1.0,                # TP1 at 1R
    "tp2_r": 2.0,                # TP2 at 2R
    "tp3_r": 3.0,                # TP3 at 3R
    "tp1_percent": 0.40,         # 40% at TP1
    "tp2_percent": 0.40,         # 40% at TP2
    "tp3_percent": 0.20          # 20% at TP3
}

# Session Times (EST hours)
SESSIONS: Dict[str, Tuple[int, int]] = {
    "london": (3, 11),    # 3am - 11am EST
    "ny": (8, 16)         # 8am - 4pm EST
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
