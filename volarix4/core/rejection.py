"""Rejection candle pattern detection module"""

import pandas as pd
from typing import Optional, Dict, List


def calculate_candle_metrics(row: pd.Series) -> Dict:
    """
    Calculate candle metrics for rejection analysis.

    Args:
        row: OHLC row from DataFrame

    Returns:
        Dict with:
        {
            'body': float,
            'upper_wick': float,
            'lower_wick': float,
            'wick_body_ratio': float,
            'close_position': float  # 0.0-1.0 (bottom to top)
        }
    """
    open_price = row['open']
    high = row['high']
    low = row['low']
    close = row['close']

    # Calculate body
    body = abs(close - open_price)

    # Calculate wicks
    if close > open_price:  # Bullish candle
        upper_wick = high - close
        lower_wick = open_price - low
    else:  # Bearish candle
        upper_wick = high - open_price
        lower_wick = close - low

    # Calculate wick/body ratio (use max wick)
    max_wick = max(upper_wick, lower_wick)
    wick_body_ratio = max_wick / body if body > 0 else 0

    # Calculate close position (0 = at low, 1 = at high)
    candle_range = high - low
    close_position = (close - low) / candle_range if candle_range > 0 else 0.5

    return {
        'body': body,
        'upper_wick': upper_wick,
        'lower_wick': lower_wick,
        'wick_body_ratio': wick_body_ratio,
        'close_position': close_position
    }


def is_support_rejection(row: pd.Series, level: float,
                        max_distance_pips: float = 10.0,
                        pip_value: float = 0.0001,
                        min_wick_ratio: float = 1.5,
                        min_close_position: float = 0.60) -> bool:
    """
    Check if candle is a valid support rejection (bullish bounce).

    Args:
        row: OHLC row from DataFrame
        level: Support level price
        max_distance_pips: Max pips from level
        pip_value: Value of 1 pip
        min_wick_ratio: Minimum wick/body ratio
        min_close_position: Close must be in top X% (0.60 = top 40%)

    Returns:
        True if valid support rejection
    """
    # Check if low touched the support level
    threshold_price = max_distance_pips * pip_value
    if abs(row['low'] - level) > threshold_price:
        return False

    # Calculate candle metrics
    metrics = calculate_candle_metrics(row)

    # Check wick/body ratio (need strong lower wick)
    if metrics['wick_body_ratio'] < min_wick_ratio:
        return False

    # Check if lower wick is the dominant one
    if metrics['lower_wick'] < metrics['upper_wick']:
        return False

    # Check close position (must close in upper portion)
    if metrics['close_position'] < min_close_position:
        return False

    return True


def is_resistance_rejection(row: pd.Series, level: float,
                           max_distance_pips: float = 10.0,
                           pip_value: float = 0.0001,
                           min_wick_ratio: float = 1.5,
                           max_close_position: float = 0.40) -> bool:
    """
    Check if candle is a valid resistance rejection (bearish reversal).

    Args:
        row: OHLC row from DataFrame
        level: Resistance level price
        max_distance_pips: Max pips from level
        pip_value: Value of 1 pip
        min_wick_ratio: Minimum wick/body ratio
        max_close_position: Close must be in bottom X% (0.40 = bottom 40%)

    Returns:
        True if valid resistance rejection
    """
    # Check if high touched the resistance level
    threshold_price = max_distance_pips * pip_value
    if abs(row['high'] - level) > threshold_price:
        return False

    # Calculate candle metrics
    metrics = calculate_candle_metrics(row)

    # Check wick/body ratio (need strong upper wick)
    if metrics['wick_body_ratio'] < min_wick_ratio:
        return False

    # Check if upper wick is the dominant one
    if metrics['upper_wick'] < metrics['lower_wick']:
        return False

    # Check close position (must close in lower portion)
    if metrics['close_position'] > max_close_position:
        return False

    return True


def find_rejection_candle(df: pd.DataFrame, levels: List[Dict],
                         lookback: int = 5,
                         pip_value: float = 0.0001) -> Optional[Dict]:
    """
    Find the most recent valid rejection candle.

    Args:
        df: DataFrame with OHLC data
        levels: List of S/R levels from detect_sr_levels()
        lookback: Number of recent candles to check
        pip_value: Value of 1 pip

    Returns:
        Rejection dict if found:
        {
            'direction': 'BUY' or 'SELL',
            'level': 1.08500,
            'level_score': 85.0,
            'entry': 1.08520,
            'candle_index': -1,
            'confidence': 0.75
        }
        or None if no valid rejection found
    """
    if not levels or len(df) < lookback:
        return None

    # Check recent candles (most recent first)
    recent_candles = df.tail(lookback)

    for idx in range(len(recent_candles) - 1, -1, -1):
        candle = recent_candles.iloc[idx]
        actual_idx = len(df) - len(recent_candles) + idx

        # Check each level for rejection
        for level_dict in levels:
            level = level_dict['level']
            level_type = level_dict['type']
            level_score = level_dict['score']

            # Check for support rejection (BUY signal)
            if level_type == 'support':
                if is_support_rejection(candle, level, pip_value=pip_value):
                    # Calculate confidence based on level score and candle quality
                    metrics = calculate_candle_metrics(candle)
                    confidence = min((level_score / 100.0 + metrics['wick_body_ratio'] / 10.0) / 2.0, 1.0)

                    return {
                        'direction': 'BUY',
                        'level': level,
                        'level_score': level_score,
                        'entry': candle['close'],
                        'candle_index': actual_idx,
                        'confidence': round(confidence, 2)
                    }

            # Check for resistance rejection (SELL signal)
            elif level_type == 'resistance':
                if is_resistance_rejection(candle, level, pip_value=pip_value):
                    # Calculate confidence based on level score and candle quality
                    metrics = calculate_candle_metrics(candle)
                    confidence = min((level_score / 100.0 + metrics['wick_body_ratio'] / 10.0) / 2.0, 1.0)

                    return {
                        'direction': 'SELL',
                        'level': level,
                        'level_score': level_score,
                        'entry': candle['close'],
                        'candle_index': actual_idx,
                        'confidence': round(confidence, 2)
                    }

    return None


# Test code
if __name__ == "__main__":
    import numpy as np

    print("Testing rejection.py module...")

    # Create sample candles
    dates = pd.date_range('2024-01-01', periods=10, freq='H')

    # Test 1: Support rejection candle
    print("\n1. Testing support rejection...")
    support_candle = pd.Series({
        'time': dates[0],
        'open': 1.08520,
        'high': 1.08550,
        'low': 1.08480,   # Touches support at 1.08500
        'close': 1.08540,  # Closes in upper portion
        'volume': 1000
    })

    is_support = is_support_rejection(support_candle, level=1.08500)
    print(f"Support rejection detected: {is_support}")

    # Test 2: Resistance rejection candle
    print("\n2. Testing resistance rejection...")
    resistance_candle = pd.Series({
        'time': dates[1],
        'open': 1.08980,
        'high': 1.09020,  # Touches resistance at 1.09000
        'low': 1.08960,
        'close': 1.08970,  # Closes in lower portion
        'volume': 1000
    })

    is_resistance = is_resistance_rejection(resistance_candle, level=1.09000)
    print(f"Resistance rejection detected: {is_resistance}")

    # Test 3: Find rejection in DataFrame
    print("\n3. Testing find_rejection_candle...")
    df = pd.DataFrame({
        'time': dates,
        'open': [1.0850 + np.random.normal(0, 0.0001) for _ in range(10)],
        'high': [1.0855 + np.random.normal(0, 0.0001) for _ in range(10)],
        'low': [1.0845 + np.random.normal(0, 0.0001) for _ in range(10)],
        'close': [1.0852 + np.random.normal(0, 0.0001) for _ in range(10)],
        'volume': [1000] * 10
    })

    # Add a clear rejection candle at the end
    df.loc[len(df)-1] = {
        'time': dates[9],
        'open': 1.08520,
        'high': 1.08550,
        'low': 1.08480,
        'close': 1.08540,
        'volume': 1000
    }

    levels = [
        {'level': 1.08500, 'score': 85.0, 'type': 'support'},
        {'level': 1.09000, 'score': 70.0, 'type': 'resistance'}
    ]

    rejection = find_rejection_candle(df, levels)
    if rejection:
        print(f"Rejection found:")
        print(f"  Direction: {rejection['direction']}")
        print(f"  Level: {rejection['level']}")
        print(f"  Confidence: {rejection['confidence']}")
    else:
        print("No rejection found")
