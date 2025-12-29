"""S/R Level Validation - Track and invalidate broken levels"""

import pandas as pd
from typing import List, Dict
from datetime import datetime, timedelta


class SRLevelValidator:
    """
    Validates S/R levels and tracks broken levels.

    A level is considered "broken" if price closes 15+ pips through it.
    Broken levels are not used for 24 hours minimum.
    """

    def __init__(self, pip_value: float = 0.0001, cooldown_hours: float = 24.0, invalidation_threshold_pips: float = 15.0):
        """
        Initialize validator.

        Args:
            pip_value: Value of 1 pip (default: 0.0001 for forex)
            cooldown_hours: Hours before broken level can be reused (default: 24.0)
            invalidation_threshold_pips: Pips to consider level broken (default: 15.0)
        """
        self.pip_value = pip_value
        self.broken_levels = {}  # {level: timestamp_broken}
        self.invalidation_threshold_pips = invalidation_threshold_pips
        self.cooldown_hours = cooldown_hours

    def is_level_broken(self, level: float, level_type: str, df: pd.DataFrame) -> bool:
        """
        Check if level has been broken by recent price action.

        Args:
            level: S/R level price
            level_type: 'support' or 'resistance'
            df: DataFrame with OHLC data

        Returns:
            True if level is broken
        """
        # Get last 10 bars
        recent_bars = df.tail(10)

        invalidation_distance = self.invalidation_threshold_pips * self.pip_value

        for _, bar in recent_bars.iterrows():
            if level_type == 'support':
                # Support is broken if price closes well below it
                if bar['close'] < (level - invalidation_distance):
                    return True

            elif level_type == 'resistance':
                # Resistance is broken if price closes well above it
                if bar['close'] > (level + invalidation_distance):
                    return True

        return False

    def mark_broken_level(self, level: float, timestamp: datetime):
        """
        Mark a level as broken.

        Args:
            level: Price level that was broken
            timestamp: When it was broken
        """
        # Round level to 5 decimals to avoid floating point issues
        level_key = round(level, 5)
        self.broken_levels[level_key] = timestamp

    def is_level_in_cooldown(self, level: float) -> tuple[bool, str]:
        """
        Check if level is still in cooldown period.

        Args:
            level: Price level to check

        Returns:
            (is_in_cooldown, reason)
        """
        level_key = round(level, 5)

        if level_key not in self.broken_levels:
            return (False, "Level not broken")

        broken_time = self.broken_levels[level_key]
        current_time = datetime.now()
        time_since_break = current_time - broken_time

        if time_since_break < timedelta(hours=self.cooldown_hours):
            hours_remaining = self.cooldown_hours - (time_since_break.total_seconds() / 3600)
            return (True, f"Level broken {time_since_break.total_seconds()/3600:.1f}h ago, {hours_remaining:.1f}h cooldown remaining")

        # Cooldown expired, remove from broken levels
        del self.broken_levels[level_key]
        return (False, "Cooldown expired")

    def validate_levels(self, levels: List[Dict], df: pd.DataFrame) -> List[Dict]:
        """
        Filter out broken and cooling down levels.

        Args:
            levels: List of S/R level dicts from detect_sr_levels()
            df: DataFrame with OHLC data

        Returns:
            Filtered list of valid levels
        """
        valid_levels = []
        current_time = datetime.now()

        for level_dict in levels:
            level = level_dict['level']
            level_type = level_dict['type']

            # Check if level is in cooldown
            in_cooldown, cooldown_reason = self.is_level_in_cooldown(level)
            if in_cooldown:
                # Skip this level
                continue

            # Check if level is currently broken
            if self.is_level_broken(level, level_type, df):
                # Mark as broken and skip
                self.mark_broken_level(level, current_time)
                continue

            # Level is valid
            valid_levels.append(level_dict)

        return valid_levels

    def cleanup_old_broken_levels(self):
        """
        Remove broken levels that have exceeded cooldown period.
        Should be called periodically.
        """
        current_time = datetime.now()
        expired_levels = []

        for level, broken_time in self.broken_levels.items():
            if current_time - broken_time > timedelta(hours=self.cooldown_hours):
                expired_levels.append(level)

        for level in expired_levels:
            del self.broken_levels[level]

        return len(expired_levels)

    def get_broken_levels_info(self) -> List[Dict]:
        """
        Get information about currently broken levels.

        Returns:
            List of dicts with level info
        """
        info = []
        current_time = datetime.now()

        for level, broken_time in self.broken_levels.items():
            time_since_break = current_time - broken_time
            hours_remaining = self.cooldown_hours - (time_since_break.total_seconds() / 3600)

            info.append({
                'level': level,
                'broken_at': broken_time.isoformat(),
                'hours_ago': round(time_since_break.total_seconds() / 3600, 1),
                'cooldown_remaining': max(0, round(hours_remaining, 1))
            })

        return info


# Test code
if __name__ == "__main__":
    import numpy as np

    print("Testing sr_validation.py module...\n")

    validator = SRLevelValidator()

    # Create sample data
    dates = pd.date_range('2024-01-01', periods=50, freq='H')
    prices = np.linspace(1.08, 1.10, 50)

    df = pd.DataFrame({
        'time': dates,
        'open': prices,
        'high': prices + 0.001,
        'low': prices - 0.001,
        'close': prices,
        'volume': [1000] * 50
    })

    # Add a price drop that breaks support
    df.loc[45:, 'close'] = 1.0780  # Drops below support at 1.09
    df.loc[45:, 'low'] = 1.0775

    print("1. Testing support level break detection...")
    support_level = 1.09000
    is_broken = validator.is_level_broken(support_level, 'support', df)
    print(f"Support at {support_level} broken: {is_broken}\n")

    # Test level validation
    print("2. Testing level validation...")
    levels = [
        {'level': 1.09000, 'score': 85.0, 'type': 'support'},
        {'level': 1.10000, 'score': 70.0, 'type': 'resistance'}
    ]

    valid_levels = validator.validate_levels(levels, df)
    print(f"Original levels: {len(levels)}")
    print(f"Valid levels: {len(valid_levels)}")
    print(f"Broken levels info: {validator.get_broken_levels_info()}\n")

    # Test cooldown
    print("3. Testing cooldown check...")
    in_cooldown, reason = validator.is_level_in_cooldown(1.09000)
    print(f"Support at 1.09000 in cooldown: {in_cooldown}")
    print(f"Reason: {reason}\n")

    # Test cleanup
    print("4. Testing cleanup...")
    # Manually set an old broken level
    old_time = datetime.now() - timedelta(hours=25)
    validator.mark_broken_level(1.08500, old_time)

    print(f"Broken levels before cleanup: {len(validator.broken_levels)}")
    cleaned = validator.cleanup_old_broken_levels()
    print(f"Cleaned {cleaned} expired levels")
    print(f"Broken levels after cleanup: {len(validator.broken_levels)}")
