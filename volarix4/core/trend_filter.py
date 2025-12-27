"""Trend filtering using EMAs to avoid counter-trend trades"""

import pandas as pd
import numpy as np
from typing import Dict, Optional


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Calculate Exponential Moving Average.

    Args:
        series: Price series (typically 'close')
        period: EMA period

    Returns:
        EMA series
    """
    return series.ewm(span=period, adjust=False).mean()


def detect_trend(df: pd.DataFrame, ema_fast: int = 20, ema_slow: int = 50) -> Dict:
    """
    Detect trend using dual EMA system.

    Trend Rules:
    - UPTREND: price > EMA20 > EMA50
    - DOWNTREND: price < EMA20 < EMA50
    - SIDEWAYS: EMAs crossed or price between EMAs

    Args:
        df: DataFrame with OHLC data
        ema_fast: Fast EMA period (default: 20)
        ema_slow: Slow EMA period (default: 50)

    Returns:
        Dict with:
        {
            'trend': 'UPTREND' | 'DOWNTREND' | 'SIDEWAYS',
            'strength': float (0.0-1.0),
            'ema_fast': float,
            'ema_slow': float,
            'current_price': float,
            'allow_buy': bool,
            'allow_sell': bool
        }
    """
    if len(df) < ema_slow + 10:
        return {
            'trend': 'SIDEWAYS',
            'strength': 0.0,
            'ema_fast': 0.0,
            'ema_slow': 0.0,
            'current_price': 0.0,
            'allow_buy': False,
            'allow_sell': False,
            'reason': f'Insufficient data (need {ema_slow + 10} bars)'
        }

    # Calculate EMAs
    df['ema_fast'] = calculate_ema(df['close'], ema_fast)
    df['ema_slow'] = calculate_ema(df['close'], ema_slow)

    # Get latest values
    current_price = df['close'].iloc[-1]
    ema_fast_val = df['ema_fast'].iloc[-1]
    ema_slow_val = df['ema_slow'].iloc[-1]

    # Determine trend
    if current_price > ema_fast_val > ema_slow_val:
        trend = 'UPTREND'
        # Calculate trend strength based on separation
        separation = (ema_fast_val - ema_slow_val) / ema_slow_val
        strength = min(separation * 100, 1.0)  # Normalize to 0-1
        allow_buy = True
        allow_sell = False
        reason = f"Price ({current_price:.5f}) > EMA{ema_fast} ({ema_fast_val:.5f}) > EMA{ema_slow} ({ema_slow_val:.5f})"

    elif current_price < ema_fast_val < ema_slow_val:
        trend = 'DOWNTREND'
        # Calculate trend strength based on separation
        separation = (ema_slow_val - ema_fast_val) / ema_slow_val
        strength = min(separation * 100, 1.0)
        allow_buy = False
        allow_sell = True
        reason = f"Price ({current_price:.5f}) < EMA{ema_fast} ({ema_fast_val:.5f}) < EMA{ema_slow} ({ema_slow_val:.5f})"

    else:
        trend = 'SIDEWAYS'
        strength = 0.0
        allow_buy = False
        allow_sell = False

        # Determine reason
        if ema_fast_val < ema_slow_val:
            reason = f"EMAs bearish but price ({current_price:.5f}) above EMA{ema_fast} ({ema_fast_val:.5f})"
        elif ema_fast_val > ema_slow_val:
            reason = f"EMAs bullish but price ({current_price:.5f}) below EMA{ema_fast} ({ema_fast_val:.5f})"
        else:
            reason = f"EMAs crossed - trend unclear"

    return {
        'trend': trend,
        'strength': round(strength, 3),
        'ema_fast': round(ema_fast_val, 5),
        'ema_slow': round(ema_slow_val, 5),
        'current_price': round(current_price, 5),
        'allow_buy': allow_buy,
        'allow_sell': allow_sell,
        'reason': reason
    }


def validate_signal_with_trend(signal_direction: str, trend_info: Dict) -> Dict:
    """
    Validate if signal direction aligns with trend.

    Args:
        signal_direction: 'BUY' or 'SELL'
        trend_info: Trend info from detect_trend()

    Returns:
        Dict with:
        {
            'valid': bool,
            'reason': str
        }
    """
    if signal_direction == 'BUY':
        if trend_info['allow_buy']:
            return {
                'valid': True,
                'reason': f"BUY signal aligns with {trend_info['trend']}"
            }
        else:
            return {
                'valid': False,
                'reason': f"BUY signal rejected - {trend_info['reason']}"
            }

    elif signal_direction == 'SELL':
        if trend_info['allow_sell']:
            return {
                'valid': True,
                'reason': f"SELL signal aligns with {trend_info['trend']}"
            }
        else:
            return {
                'valid': False,
                'reason': f"SELL signal rejected - {trend_info['reason']}"
            }

    return {
        'valid': False,
        'reason': 'Invalid signal direction'
    }


# Test code
if __name__ == "__main__":
    print("Testing trend_filter.py module...\n")

    # Create sample data with uptrend
    print("1. Testing UPTREND detection...")
    dates = pd.date_range('2024-01-01', periods=100, freq='H')
    uptrend_prices = np.linspace(1.08, 1.10, 100) + np.random.normal(0, 0.0005, 100)

    df_up = pd.DataFrame({
        'time': dates,
        'open': uptrend_prices,
        'high': uptrend_prices + 0.0005,
        'low': uptrend_prices - 0.0005,
        'close': uptrend_prices,
        'volume': [1000] * 100
    })

    trend = detect_trend(df_up)
    print(f"Trend: {trend['trend']}")
    print(f"Strength: {trend['strength']}")
    print(f"Allow BUY: {trend['allow_buy']}, Allow SELL: {trend['allow_sell']}")
    print(f"Reason: {trend['reason']}\n")

    # Test signal validation
    print("2. Testing signal validation with uptrend...")
    buy_validation = validate_signal_with_trend('BUY', trend)
    print(f"BUY signal: Valid={buy_validation['valid']}, Reason={buy_validation['reason']}")

    sell_validation = validate_signal_with_trend('SELL', trend)
    print(f"SELL signal: Valid={sell_validation['valid']}, Reason={sell_validation['reason']}\n")

    # Create sample data with downtrend
    print("3. Testing DOWNTREND detection...")
    downtrend_prices = np.linspace(1.10, 1.08, 100) + np.random.normal(0, 0.0005, 100)

    df_down = pd.DataFrame({
        'time': dates,
        'open': downtrend_prices,
        'high': downtrend_prices + 0.0005,
        'low': downtrend_prices - 0.0005,
        'close': downtrend_prices,
        'volume': [1000] * 100
    })

    trend_down = detect_trend(df_down)
    print(f"Trend: {trend_down['trend']}")
    print(f"Allow BUY: {trend_down['allow_buy']}, Allow SELL: {trend_down['allow_sell']}")
    print(f"Reason: {trend_down['reason']}")
