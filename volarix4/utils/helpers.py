"""Utility functions for Volarix 4"""

import logging
from datetime import datetime
from typing import Optional
import pytz


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configure logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger("volarix4")
    return logger


def calculate_pip_value(symbol: str) -> float:
    """
    Get pip value for symbol.

    Args:
        symbol: Trading pair (e.g., "EURUSD", "USDJPY")

    Returns:
        0.0001 for major pairs (EURUSD, GBPUSD, etc)
        0.01 for JPY pairs (USDJPY, EURJPY, etc)
        0.0001 for unknown pairs (default)
    """
    # Check if symbol contains JPY
    if "JPY" in symbol.upper():
        return 0.01
    else:
        return 0.0001


def pips_to_price(pips: float, symbol: str) -> float:
    """
    Convert pips to price difference.

    Args:
        pips: Number of pips
        symbol: Trading pair

    Returns:
        Price difference equivalent to pips
    """
    pip_value = calculate_pip_value(symbol)
    return pips * pip_value


def price_to_pips(price_diff: float, symbol: str) -> float:
    """
    Convert price difference to pips.

    Args:
        price_diff: Price difference
        symbol: Trading pair

    Returns:
        Number of pips
    """
    pip_value = calculate_pip_value(symbol)
    return price_diff / pip_value


def get_current_est_hour() -> int:
    """
    Get current hour in EST timezone.

    Returns:
        Hour in EST (0-23)
    """
    est = pytz.timezone('US/Eastern')
    now_est = datetime.now(est)
    return now_est.hour


def format_price(price: float, symbol: str) -> str:
    """
    Format price with appropriate decimal places.

    Args:
        price: Price value
        symbol: Trading pair

    Returns:
        Formatted price string
    """
    if "JPY" in symbol.upper():
        return f"{price:.3f}"
    else:
        return f"{price:.5f}"


# Test code
if __name__ == "__main__":
    print("Testing utils.py module...")

    # Test 1: Logging setup
    print("\n1. Testing logging setup...")
    logger = setup_logging("ERROR")
    logger.info("Logger initialized successfully")
    logger.debug("This debug message won't show at INFO level")

    # Test 2: Pip value calculation
    print("\n2. Testing pip value calculation...")
    eurusd_pip = calculate_pip_value("EURUSD")
    usdjpy_pip = calculate_pip_value("USDJPY")
    print(f"EURUSD pip value: {eurusd_pip}")
    print(f"USDJPY pip value: {usdjpy_pip}")

    # Test 3: Pip/price conversion
    print("\n3. Testing pip/price conversion...")
    price_diff = pips_to_price(10, "EURUSD")
    pips = price_to_pips(0.0010, "EURUSD")
    print(f"10 pips in EURUSD = {price_diff}")
    print(f"0.0010 in EURUSD = {pips} pips")

    # Test 4: EST hour
    print("\n4. Testing EST hour...")
    est_hour = get_current_est_hour()
    print(f"Current EST hour: {est_hour}")

    # Test 5: Price formatting
    print("\n5. Testing price formatting...")
    eurusd_price = format_price(1.08525, "EURUSD")
    usdjpy_price = format_price(145.235, "USDJPY")
    print(f"EURUSD: {eurusd_price}")
    print(f"USDJPY: {usdjpy_price}")
