"""Data source for loading historical OHLCV bars.

This module loads bars from local files or MT5, but does NOT call any
strategy logic (volarix4.core.*). It only provides raw bar data.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Optional, List
import pandas as pd


@dataclass
class Bar:
    """Represents a single OHLCV bar."""

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def to_dict(self) -> dict:
        """Convert to dictionary for API payload."""
        return {
            "time": int(self.time.timestamp()),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume
        }


class BarDataSource:
    """Loads historical bars from various sources.

    Supports:
    - CSV files (time, open, high, low, close, volume)
    - Parquet files
    - MT5 via volarix4.core.data.fetch_ohlc (but only for data loading, NOT strategy)
    """

    def __init__(
        self,
        source: str,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bars: Optional[int] = None,
        file_path: Optional[str] = None
    ):
        """Initialize data source.

        Args:
            source: "csv", "parquet", or "mt5"
            symbol: Trading symbol (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "H1", "M15", "D1")
            start_date: Start date for filtering (optional)
            end_date: End date for filtering (optional)
            bars: Number of most recent bars to load (alternative to date range)
            file_path: Path to CSV/Parquet file (optional, stored for later use)
        """
        self.source = source
        self.symbol = symbol
        self.timeframe = timeframe
        self.start_date = start_date
        self.end_date = end_date
        self.bars = bars
        self.file_path = file_path
        self._data: Optional[pd.DataFrame] = None

    def load(self, file_path: Optional[str] = None) -> List[Bar]:
        """Load bars from the configured source.

        Args:
            file_path: Path to CSV/Parquet file (overrides self.file_path if provided)

        Returns:
            List of Bar objects sorted by time (ascending)

        Raises:
            ValueError: If source is invalid or file_path is missing
        """
        # Use provided file_path or fall back to stored file_path
        path = file_path or self.file_path

        if self.source == "csv":
            if not path:
                raise ValueError("file_path required for CSV source")
            df = self._load_csv(path)
        elif self.source == "parquet":
            if not path:
                raise ValueError("file_path required for Parquet source")
            df = self._load_parquet(path)
        elif self.source == "mt5":
            df = self._load_mt5()
        else:
            raise ValueError(f"Invalid source: {self.source}. Must be 'csv', 'parquet', or 'mt5'")

        # Apply date filtering
        df = self._filter_by_dates(df)

        # Apply bar limit
        if self.bars is not None:
            df = df.tail(self.bars)

        # Store and convert to Bar objects
        self._data = df
        return self._df_to_bars(df)

    def _load_csv(self, file_path: str) -> pd.DataFrame:
        """Load bars from CSV file."""
        df = pd.read_csv(file_path)

        # Ensure required columns exist
        required = ["time", "open", "high", "low", "close", "volume"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        # Convert time to datetime
        df['time'] = pd.to_datetime(df['time'])

        # Sort by time
        df = df.sort_values('time').reset_index(drop=True)

        return df[required]

    def _load_parquet(self, file_path: str) -> pd.DataFrame:
        """Load bars from Parquet file."""
        df = pd.read_parquet(file_path)

        # Ensure required columns exist
        required = ["time", "open", "high", "low", "close", "volume"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Parquet missing required columns: {missing}")

        # Convert time to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(df['time']):
            df['time'] = pd.to_datetime(df['time'])

        # Sort by time
        df = df.sort_values('time').reset_index(drop=True)

        return df[required]

    def _load_mt5(self) -> pd.DataFrame:
        """Load bars from MT5.

        Note: This imports fetch_ohlc from volarix4.core.data, but ONLY for
        data loading purposes. No strategy logic is called.
        """
        try:
            from volarix4.core.data import fetch_ohlc
        except ImportError:
            raise ImportError(
                "Cannot import fetch_ohlc from volarix4.core.data. "
                "MT5 data source requires volarix4 package."
            )

        # Determine number of bars to fetch
        if self.bars is not None:
            num_bars = self.bars
        elif self.start_date and self.end_date:
            # Estimate bars needed (conservative: assume 1 bar per hour for H1)
            # This is a rough estimate - fetch_ohlc will handle the actual date range
            num_bars = 10000  # Fetch a large number and filter later
        else:
            num_bars = 5000  # Default

        # Fetch bars
        df = fetch_ohlc(
            symbol=self.symbol,
            timeframe=self.timeframe,
            bars=num_bars,
            end_time=self.end_date
        )

        if df is None or len(df) == 0:
            raise ValueError(f"Failed to fetch bars from MT5 for {self.symbol} {self.timeframe}")

        return df

    def _filter_by_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter DataFrame by start/end dates."""
        if self.start_date:
            df = df[df['time'] >= self.start_date]

        if self.end_date:
            df = df[df['time'] <= self.end_date]

        return df.reset_index(drop=True)

    def _df_to_bars(self, df: pd.DataFrame) -> List[Bar]:
        """Convert DataFrame to list of Bar objects."""
        bars = []
        for _, row in df.iterrows():
            bars.append(Bar(
                time=row['time'],
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=int(row['volume'])
            ))
        return bars

    def get_dataframe(self) -> pd.DataFrame:
        """Get the loaded data as a pandas DataFrame.

        Returns:
            DataFrame with columns: time, open, high, low, close, volume

        Raises:
            ValueError: If data hasn't been loaded yet
        """
        if self._data is None:
            raise ValueError("Data not loaded. Call load() first.")
        return self._data.copy()
