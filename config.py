"""Configuration settings for Volarix 4"""

CONFIG = {
    # MT5 Connection
    "mt5_login": 123456,
    "mt5_password": "password",
    "mt5_server": "Broker-Server",

    # Trading Sessions (EST hours)
    "sessions": {
        "london": (3, 11),
        "ny": (8, 16)
    },

    # S/R Level Detection
    "sr_lookback": 50,
    "min_touches": 3,
    "touch_threshold_pips": 10,

    # Rejection Candle Criteria
    "wick_body_ratio": 1.5,
    "close_zone_percent": 0.4,

    # Risk Management
    "sl_pips_beyond": 10,
    "tp_ratios": [1, 2, 3],
    "tp_percents": [0.4, 0.4, 0.2],
}
