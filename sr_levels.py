"""Support/Resistance level detection module"""

import pandas as pd
import numpy as np
from typing import List, Dict


def find_swing_highs(df: pd.DataFrame, window: int = 5) -> List[int]:
    """
    Find swing high indices in price data.

    Args:
        df: DataFrame with OHLC data
        window: Lookback window for swing detection

    Returns:
        List of indices where swing highs occur
    """
    swing_highs = []
    highs = df['high'].values

    for i in range(window, len(highs) - window):
        # Check if current high is highest in window
        left_max = max(highs[i-window:i])
        right_max = max(highs[i+1:i+window+1])

        if highs[i] > left_max and highs[i] > right_max:
            swing_highs.append(i)

    return swing_highs


def find_swing_lows(df: pd.DataFrame, window: int = 5) -> List[int]:
    """
    Find swing low indices in price data.

    Args:
        df: DataFrame with OHLC data
        window: Lookback window for swing detection

    Returns:
        List of indices where swing lows occur
    """
    swing_lows = []
    lows = df['low'].values

    for i in range(window, len(lows) - window):
        # Check if current low is lowest in window
        left_min = min(lows[i-window:i])
        right_min = min(lows[i+1:i+window+1])

        if lows[i] < left_min and lows[i] < right_min:
            swing_lows.append(i)

    return swing_lows


def cluster_levels(levels: List[float], pip_threshold: float = 10.0,
                   pip_value: float = 0.0001) -> List[float]:
    """
    Cluster nearby price levels within pip threshold.

    Args:
        levels: List of price levels
        pip_threshold: Maximum pips between levels to cluster
        pip_value: Value of 1 pip (0.0001 for most pairs)

    Returns:
        List of clustered levels (averaged)
    """
    if not levels:
        return []

    sorted_levels = sorted(levels)
    clustered = []
    current_cluster = [sorted_levels[0]]
    threshold_price = pip_threshold * pip_value

    for level in sorted_levels[1:]:
        if level - current_cluster[-1] <= threshold_price:
            current_cluster.append(level)
        else:
            # Average the cluster and start new one
            clustered.append(np.mean(current_cluster))
            current_cluster = [level]

    # Add final cluster
    if current_cluster:
        clustered.append(np.mean(current_cluster))

    return clustered


def count_touches(level: float, df: pd.DataFrame, pip_threshold: float = 10.0,
                  pip_value: float = 0.0001) -> int:
    """
    Count how many times price touched a level.

    Args:
        level: S/R level price
        df: DataFrame with OHLC data
        pip_threshold: Max distance to count as touch
        pip_value: Value of 1 pip

    Returns:
        Number of touches
    """
    threshold_price = pip_threshold * pip_value
    touches = 0

    for _, row in df.iterrows():
        # Check if high or low touched the level
        if abs(row['high'] - level) <= threshold_price or \
           abs(row['low'] - level) <= threshold_price:
            touches += 1

    return touches


def score_level(level: float, df: pd.DataFrame, level_type: str,
                pip_value: float = 0.0001) -> float:
    """
    Calculate quality score for S/R level (0-100).

    Scoring:
    - Base: 20 points per touch
    - Recent touch (last 20 bars): +50 points
    - Strong rejection: +20 points

    Args:
        level: S/R level price
        df: DataFrame with OHLC data
        level_type: 'support' or 'resistance'
        pip_value: Value of 1 pip

    Returns:
        Score (0-100)
    """
    touches = count_touches(level, df, pip_threshold=10.0, pip_value=pip_value)
    score = touches * 20.0

    # Check for recent touch (last 20 bars)
    recent_df = df.tail(20)
    recent_touches = count_touches(level, recent_df, pip_threshold=10.0, pip_value=pip_value)
    if recent_touches > 0:
        score += 50.0

    # Check for strong rejection (large wick at level)
    threshold_price = 10.0 * pip_value
    for _, row in recent_df.iterrows():
        body = abs(row['close'] - row['open'])

        if level_type == 'support':
            lower_wick = row['open'] - row['low'] if row['close'] > row['open'] else row['close'] - row['low']
            if abs(row['low'] - level) <= threshold_price and lower_wick > body * 1.5:
                score += 20.0
                break
        else:  # resistance
            upper_wick = row['high'] - row['close'] if row['close'] < row['open'] else row['high'] - row['open']
            if abs(row['high'] - level) <= threshold_price and upper_wick > body * 1.5:
                score += 20.0
                break

    return min(score, 100.0)


def detect_sr_levels(df: pd.DataFrame, min_score: float = 60.0,
                     pip_value: float = 0.0001) -> List[Dict]:
    """
    Detect and score S/R levels from OHLC data.

    Args:
        df: DataFrame with OHLC data
        min_score: Minimum score to include level
        pip_value: Value of 1 pip

    Returns:
        List of level dicts: [{'level': 1.08500, 'score': 85.0, 'type': 'support'}, ...]
    """
    # Find swing points
    swing_high_indices = find_swing_highs(df, window=5)
    swing_low_indices = find_swing_lows(df, window=5)

    # Extract prices
    resistance_prices = [df.iloc[i]['high'] for i in swing_high_indices]
    support_prices = [df.iloc[i]['low'] for i in swing_low_indices]

    # Cluster levels
    clustered_resistance = cluster_levels(resistance_prices, pip_threshold=10.0, pip_value=pip_value)
    clustered_support = cluster_levels(support_prices, pip_threshold=10.0, pip_value=pip_value)

    # Score and filter levels
    levels = []

    for level in clustered_support:
        score = score_level(level, df, 'support', pip_value)
        if score >= min_score:
            levels.append({
                'level': round(level, 5),
                'score': round(score, 1),
                'type': 'support'
            })

    for level in clustered_resistance:
        score = score_level(level, df, 'resistance', pip_value)
        if score >= min_score:
            levels.append({
                'level': round(level, 5),
                'score': round(score, 1),
                'type': 'resistance'
            })

    # Sort by score descending
    levels.sort(key=lambda x: x['score'], reverse=True)

    return levels


# Test code
if __name__ == "__main__":
    print("Testing sr_levels.py module...")

    # Create sample OHLC data
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='H')

    # Simulate price movement with S/R levels at 1.0850 and 1.0900
    base_price = 1.0875
    noise = np.random.normal(0, 0.0010, 100)
    prices = base_price + noise

    df = pd.DataFrame({
        'time': dates,
        'open': prices,
        'high': prices + np.abs(np.random.normal(0, 0.0005, 100)),
        'low': prices - np.abs(np.random.normal(0, 0.0005, 100)),
        'close': prices + np.random.normal(0, 0.0003, 100),
        'volume': np.random.randint(100, 1000, 100)
    })

    print("\n1. Finding swing highs and lows...")
    highs = find_swing_highs(df)
    lows = find_swing_lows(df)
    print(f"Found {len(highs)} swing highs and {len(lows)} swing lows")

    print("\n2. Detecting S/R levels...")
    levels = detect_sr_levels(df, min_score=40.0)

    if levels:
        print(f"\nDetected {len(levels)} S/R levels:")
        for level in levels[:5]:  # Show top 5
            print(f"  {level['type'].upper()}: {level['level']:.5f} (score: {level['score']})")
    else:
        print("No levels detected (expected with random data)")
