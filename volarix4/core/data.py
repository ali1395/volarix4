"""MT5 data fetching module"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
from typing import Optional
from volarix4.config import CONFIG


def connect_mt5() -> bool:
    """
    Connect to MT5 terminal using credentials from config.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        if not mt5.initialize():
            print(f"MT5 initialize() failed, error code: {mt5.last_error()}")
            return False

        # Login with credentials
        # authorized = mt5.login(
        #     login=CONFIG["mt5_login"],
        #     password=CONFIG["mt5_password"],
        #     server=CONFIG["mt5_server"]
        # )
        #
        # if not authorized:
        #     print(f"MT5 login failed, error code: {mt5.last_error()}")
        #     mt5.shutdown()
        #     return False

        return True
    except Exception as e:
        print(f"MT5 connection error: {e}")
        return False


def _timeframe_to_mt5(timeframe: str) -> Optional[int]:
    """
    Convert timeframe string to MT5 constant.

    Args:
        timeframe: String like "M1", "M5", "H1", "D1"

    Returns:
        MT5 timeframe constant or None if invalid
    """
    timeframes = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
    }
    return timeframes.get(timeframe.upper())


def fetch_ohlc(symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
    """
    Fetch OHLC data from MT5.

    Args:
        symbol: Trading pair (e.g., "EURUSD")
        timeframe: MT5 timeframe (e.g., "H1", "M30")
        bars: Number of bars to fetch

    Returns:
        DataFrame with columns: time, open, high, low, close, volume

    Raises:
        Exception if connection fails or data fetch fails
    """
    # Ensure MT5 is connected
    if not mt5.terminal_info():
        if not connect_mt5():
            raise Exception("Failed to connect to MT5")

    # Convert timeframe
    mt5_timeframe = _timeframe_to_mt5(timeframe)
    if mt5_timeframe is None:
        raise ValueError(f"Invalid timeframe: {timeframe}")

    # Fetch data from current position (most recent bars)
    rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, bars)

    if rates is None or len(rates) == 0:
        raise Exception(f"Failed to fetch data for {symbol}, error: {mt5.last_error()}")

    # Convert to DataFrame
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')

    # Keep only required columns
    df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume']]
    df.rename(columns={'tick_volume': 'volume'}, inplace=True)

    return df


def is_valid_session(timestamp: pd.Timestamp) -> bool:
    """
    Check if timestamp is within London or NY session (EST).

    Args:
        timestamp: Pandas Timestamp to check

    Returns:
        True if within trading session, False otherwise
    """
    # Convert to EST if needed (assuming UTC input)
    # For simplicity, we'll use the hour directly
    hour = timestamp.hour

    # London session: 3-11 EST
    london_start, london_end = CONFIG["sessions"]["london"]
    # NY session: 8-16 EST
    ny_start, ny_end = CONFIG["sessions"]["ny"]

    # Check if hour falls within either session
    in_london = london_start <= hour < london_end
    in_ny = ny_start <= hour < ny_end

    return in_london or in_ny


# Test code
if __name__ == "__main__":
    print("Testing data.py module...")

    # Test 1: Connect to MT5
    print("\n1. Testing MT5 connection...")
    connected = connect_mt5()
    print(f"Connection status: {connected}")

    if connected:
        # Test 2: Fetch OHLC data
        print("\n2. Testing OHLC data fetch...")
        try:
            df = fetch_ohlc("EURUSD", "H1", 400)
            print(f"Fetched {len(df)} bars")
            print(f"Columns: {df.columns.tolist()}")
            print(f"\nFirst 3 bars:")
            print(df.head(3))
            print(f"\nLast 3 bars:")
            print(df.tail(3))

            # Test 3: Session validation
            print("\n3. Testing session validation...")
            for i in range(24):
                test_time = pd.Timestamp(f"2024-01-01 {i:02d}:00:00")
                valid = is_valid_session(test_time)
                if valid:
                    print(f"Hour {i:02d}:00 EST - Valid session")

        except Exception as e:
            print(f"Error: {e}")

        mt5.shutdown()
        print("\nMT5 connection closed.")
    else:
        print("Could not test data fetching - connection failed")
        print("This is expected if MT5 is not running or credentials are invalid")
