"""
Bar Validation and Normalization - Parity Contract Enforcement

This module ensures all bars received by the API conform to the Parity Contract:
- Strictly increasing timestamps (oldest → newest)
- No duplicates
- Timeframe-aligned gaps
- Sufficient lookback
- All bars are closed (not forming)
"""

from typing import List, Dict, Tuple
from datetime import datetime
import pandas as pd


# Timeframe to seconds mapping
TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
    "W1": 604800,
}


class BarValidationError(Exception):
    """Raised when bars violate Parity Contract"""
    pass


def get_timeframe_seconds(timeframe: str) -> int:
    """
    Get timeframe period in seconds.

    Args:
        timeframe: Timeframe string (M1, M5, M15, M30, H1, H4, D1, W1)

    Returns:
        Period in seconds

    Raises:
        BarValidationError: If timeframe is invalid
    """
    tf_upper = timeframe.upper()
    if tf_upper not in TIMEFRAME_SECONDS:
        raise BarValidationError(
            f"Invalid timeframe '{timeframe}'. "
            f"Must be one of: {', '.join(TIMEFRAME_SECONDS.keys())}"
        )
    return TIMEFRAME_SECONDS[tf_upper]


def normalize_and_validate_bars(
    bars: List[Dict],
    timeframe: str,
    min_bars: int = 200,
    allow_gap_tolerance: bool = True,
    max_gap_multiplier: int = 168  # 1 week = 168 hours (allows weekends + holidays)
) -> Tuple[List[Dict], Dict]:
    """
    Canonical bar normalization and validation per Parity Contract.

    Validation Rules (hard-fail):
    1. Minimum bar count (>= min_bars, typically 200 for lookback)
    2. No time == 0 (invalid bars)
    3. Strictly increasing timestamps (oldest → newest)
    4. No duplicate timestamps
    5. Timeframe-aligned gaps (with tolerance for weekends/holidays)

    Args:
        bars: List of bar dicts with 'time', 'open', 'high', 'low', 'close', 'volume'
        timeframe: Timeframe string (M1, H1, etc.)
        min_bars: Minimum required bars for lookback
        allow_gap_tolerance: Allow gaps for weekends/holidays (strongly recommended)
        max_gap_multiplier: Maximum allowed gap as multiple of timeframe period
                           Default 168 = 1 week (168 hours for H1, allows long weekends)

    Returns:
        Tuple of (validated_bars, metadata_dict)
        metadata_dict contains:
            - first_time: First bar timestamp
            - last_time: Last bar timestamp
            - decision_bar_time: Decision bar timestamp (last closed bar)
            - decision_bar_close: Decision bar close price
            - bar_count: Number of bars
            - timeframe_seconds: Timeframe period in seconds

    Raises:
        BarValidationError: If any validation rule is violated
    """
    # Get timeframe period
    tf_seconds = get_timeframe_seconds(timeframe)

    # Rule 1: Minimum bar count
    if len(bars) < min_bars:
        raise BarValidationError(
            f"Insufficient bars: got {len(bars)}, required {min_bars} for lookback. "
            f"Parity Contract requires at least {min_bars} closed bars."
        )

    # Rule 2 & 3: Check each bar
    for i, bar in enumerate(bars):
        # Check for time == 0
        if bar['time'] == 0:
            raise BarValidationError(
                f"Invalid bar at index {i}: time == 0. "
                f"All bars must have valid timestamps."
            )

        # Check for strictly increasing (no duplicates, no backward time)
        if i > 0:
            prev_time = bars[i - 1]['time']
            curr_time = bar['time']

            if curr_time <= prev_time:
                raise BarValidationError(
                    f"Bars not strictly increasing at index {i}: "
                    f"bar[{i-1}].time={prev_time} ({datetime.fromtimestamp(prev_time)}), "
                    f"bar[{i}].time={curr_time} ({datetime.fromtimestamp(curr_time)}). "
                    f"Delta: {curr_time - prev_time} seconds. "
                    f"Bars must be ordered oldest → newest with no duplicates."
                )

            # Rule 5: Check timeframe alignment
            time_delta = curr_time - prev_time

            # Exact alignment check
            if time_delta % tf_seconds != 0:
                raise BarValidationError(
                    f"Timeframe misalignment at index {i}: "
                    f"gap of {time_delta} seconds is not a multiple of {tf_seconds}. "
                    f"Expected multiples of {tf_seconds} ({timeframe}) but got {time_delta}."
                )

            # Gap size check (allow small gaps for weekends/holidays if enabled)
            gap_multiplier = time_delta // tf_seconds

            if not allow_gap_tolerance and gap_multiplier != 1:
                raise BarValidationError(
                    f"Non-consecutive bars at index {i}: "
                    f"gap of {gap_multiplier} periods ({time_delta} seconds). "
                    f"Consecutive bars required (gap tolerance disabled)."
                )

            if allow_gap_tolerance and gap_multiplier > max_gap_multiplier:
                raise BarValidationError(
                    f"Excessive gap at index {i}: "
                    f"gap of {gap_multiplier} periods ({time_delta} seconds) "
                    f"exceeds max allowed {max_gap_multiplier} periods. "
                    f"This suggests missing data or discontinuous history."
                )

    # All validation passed - extract metadata
    first_time = bars[0]['time']
    last_time = bars[-1]['time']
    decision_bar_time = last_time  # Per Parity Contract: decision at last closed bar
    decision_bar_close = bars[-1]['close']

    metadata = {
        'first_time': first_time,
        'last_time': last_time,
        'decision_bar_time': decision_bar_time,
        'decision_bar_close': decision_bar_close,
        'bar_count': len(bars),
        'timeframe_seconds': tf_seconds,
        'first_datetime': datetime.fromtimestamp(first_time),
        'last_datetime': datetime.fromtimestamp(last_time),
        'decision_datetime': datetime.fromtimestamp(decision_bar_time),
    }

    return bars, metadata


def log_bar_validation_summary(logger, metadata: Dict, symbol: str, timeframe: str):
    """
    Log standardized bar validation summary (request echo debug).

    Args:
        logger: Logger instance
        metadata: Metadata dict from normalize_and_validate_bars()
        symbol: Trading symbol
        timeframe: Timeframe string
    """
    logger.info("=" * 70)
    logger.info("BAR VALIDATION SUMMARY (Parity Contract)")
    logger.info("=" * 70)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Timeframe: {timeframe} ({metadata['timeframe_seconds']} seconds)")
    logger.info(f"Bar count: {metadata['bar_count']}")
    logger.info(f"First bar time: {metadata['first_datetime']} (timestamp: {metadata['first_time']})")
    logger.info(f"Last bar time: {metadata['last_datetime']} (timestamp: {metadata['last_time']})")
    logger.info(f"Decision bar time: {metadata['decision_datetime']} (timestamp: {metadata['decision_bar_time']})")
    logger.info(f"Decision bar close: {metadata['decision_bar_close']:.5f}")

    # Calculate bar span
    total_span_seconds = metadata['last_time'] - metadata['first_time']
    expected_bars = (total_span_seconds // metadata['timeframe_seconds']) + 1
    logger.info(f"Time span: {total_span_seconds} seconds ({total_span_seconds / 3600:.1f} hours)")
    logger.info(f"Expected bars (if no gaps): {expected_bars}")

    if metadata['bar_count'] < expected_bars:
        gap_count = expected_bars - metadata['bar_count']
        logger.warning(f"Gap detected: {gap_count} bars missing (weekends/holidays expected)")

    logger.info("Validation: PASSED")
    logger.info("=" * 70)


def validate_decision_bar_closed(
    decision_bar_time: int,
    current_time: int,
    timeframe_seconds: int,
    logger
) -> bool:
    """
    Validate that the decision bar is fully closed (not forming).

    Per Parity Contract: The decision bar must be at least 1 full period old.

    Args:
        decision_bar_time: Decision bar timestamp
        current_time: Current server timestamp
        timeframe_seconds: Timeframe period in seconds
        logger: Logger instance

    Returns:
        True if closed, False if potentially forming
    """
    bar_age_seconds = current_time - decision_bar_time
    is_closed = bar_age_seconds >= timeframe_seconds

    if not is_closed:
        logger.warning(
            f"Decision bar age ({bar_age_seconds}s) < timeframe ({timeframe_seconds}s). "
            f"Bar may be forming! Ensure MT5 EA sends only closed bars (CopyRates shift=1)."
        )

    return is_closed
