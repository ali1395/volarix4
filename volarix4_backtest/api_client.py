"""API client for calling the Volarix 4 /signal endpoint.

This module handles all communication with the FastAPI signal endpoint,
including retries, timeouts, and error handling.
"""

from dataclasses import dataclass
from typing import List, Optional, Literal
from datetime import datetime
import requests
import time
import logging


@dataclass
class SignalResponse:
    """Response from /signal endpoint."""

    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    tp1_percent: float
    tp2_percent: float
    tp3_percent: float
    reason: str

    @classmethod
    def from_dict(cls, data: dict) -> "SignalResponse":
        """Create SignalResponse from API response dictionary."""
        return cls(
            signal=data["signal"],
            confidence=data["confidence"],
            entry=data["entry"],
            sl=data["sl"],
            tp1=data["tp1"],
            tp2=data["tp2"],
            tp3=data["tp3"],
            tp1_percent=data["tp1_percent"],
            tp2_percent=data["tp2_percent"],
            tp3_percent=data["tp3_percent"],
            reason=data["reason"]
        )


class SignalApiClient:
    """Client for calling the Volarix 4 /signal endpoint.

    Supports both optimized mode (bar_time) and legacy mode (data array).
    Handles retries, timeouts, and logging.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize API client.

        Args:
            base_url: Base URL of the API (e.g., "http://localhost:8000")
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries on failure
            retry_delay: Delay between retries in seconds
            logger: Optional logger for request/response logging
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logger or logging.getLogger(__name__)

        # Create session for connection pooling (HUGE performance boost!)
        self.session = requests.Session()

        # Stats tracking
        self.total_requests = 0
        self.failed_requests = 0
        self.total_retry_count = 0

    def get_signal_optimized(
        self,
        symbol: str,
        timeframe: str,
        bar_time: datetime,
        lookback_bars: int = 400,
        min_confidence: Optional[float] = None,
        broken_level_cooldown_hours: Optional[float] = None,
        broken_level_break_pips: Optional[float] = None,
        min_edge_pips: Optional[float] = None,
        spread_pips: Optional[float] = None,
        slippage_pips: Optional[float] = None,
        commission_per_side_per_lot: Optional[float] = None,
        usd_per_pip_per_lot: Optional[float] = None,
        lot_size: Optional[float] = None
    ) -> SignalResponse:
        """Get signal using optimized mode (API fetches bars).

        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "H1", "M15")
            bar_time: Timestamp of the bar to generate signal for
            lookback_bars: Number of bars before bar_time to fetch
            min_confidence: Minimum confidence threshold (parity param)
            broken_level_cooldown_hours: Broken level cooldown (parity param)
            broken_level_break_pips: Broken level break threshold (parity param)
            min_edge_pips: Minimum edge after costs (parity param)
            spread_pips: Spread cost (parity param)
            slippage_pips: Slippage cost (parity param)
            commission_per_side_per_lot: Commission cost (parity param)
            usd_per_pip_per_lot: USD per pip per lot (parity param)
            lot_size: Lot size (parity param)

        Returns:
            SignalResponse with BUY/SELL/HOLD and trade parameters

        Raises:
            requests.RequestException: If request fails after retries
        """
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "bar_time": int(bar_time.timestamp()),
            "lookback_bars": lookback_bars
        }

        # Add optional parity parameters
        if min_confidence is not None:
            payload["min_confidence"] = min_confidence
        if broken_level_cooldown_hours is not None:
            payload["broken_level_cooldown_hours"] = broken_level_cooldown_hours
        if broken_level_break_pips is not None:
            payload["broken_level_break_pips"] = broken_level_break_pips
        if min_edge_pips is not None:
            payload["min_edge_pips"] = min_edge_pips
        if spread_pips is not None:
            payload["spread_pips"] = spread_pips
        if slippage_pips is not None:
            payload["slippage_pips"] = slippage_pips
        if commission_per_side_per_lot is not None:
            payload["commission_per_side_per_lot"] = commission_per_side_per_lot
        if usd_per_pip_per_lot is not None:
            payload["usd_per_pip_per_lot"] = usd_per_pip_per_lot
        if lot_size is not None:
            payload["lot_size"] = lot_size

        return self._request(payload)

    def get_signal_legacy(
        self,
        symbol: str,
        timeframe: str,
        bars: List[dict],
        min_confidence: Optional[float] = None,
        broken_level_cooldown_hours: Optional[float] = None,
        broken_level_break_pips: Optional[float] = None,
        min_edge_pips: Optional[float] = None,
        spread_pips: Optional[float] = None,
        slippage_pips: Optional[float] = None,
        commission_per_side_per_lot: Optional[float] = None,
        usd_per_pip_per_lot: Optional[float] = None,
        lot_size: Optional[float] = None
    ) -> SignalResponse:
        """Get signal using legacy mode (send full bar data).

        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "H1", "M15")
            bars: List of bar dicts with keys: time, open, high, low, close, volume
            min_confidence: Minimum confidence threshold (parity param)
            broken_level_cooldown_hours: Broken level cooldown (parity param)
            broken_level_break_pips: Broken level break threshold (parity param)
            min_edge_pips: Minimum edge after costs (parity param)
            spread_pips: Spread cost (parity param)
            slippage_pips: Slippage cost (parity param)
            commission_per_side_per_lot: Commission cost (parity param)
            usd_per_pip_per_lot: USD per pip per lot (parity param)
            lot_size: Lot size (parity param)

        Returns:
            SignalResponse with BUY/SELL/HOLD and trade parameters

        Raises:
            requests.RequestException: If request fails after retries
        """
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "data": bars
        }

        # Add optional parity parameters
        if min_confidence is not None:
            payload["min_confidence"] = min_confidence
        if broken_level_cooldown_hours is not None:
            payload["broken_level_cooldown_hours"] = broken_level_cooldown_hours
        if broken_level_break_pips is not None:
            payload["broken_level_break_pips"] = broken_level_break_pips
        if min_edge_pips is not None:
            payload["min_edge_pips"] = min_edge_pips
        if spread_pips is not None:
            payload["spread_pips"] = spread_pips
        if slippage_pips is not None:
            payload["slippage_pips"] = slippage_pips
        if commission_per_side_per_lot is not None:
            payload["commission_per_side_per_lot"] = commission_per_side_per_lot
        if usd_per_pip_per_lot is not None:
            payload["usd_per_pip_per_lot"] = usd_per_pip_per_lot
        if lot_size is not None:
            payload["lot_size"] = lot_size

        return self._request(payload)

    def _request(self, payload: dict) -> SignalResponse:
        """Make POST request to /signal with retries.

        Args:
            payload: Request payload dictionary

        Returns:
            SignalResponse

        Raises:
            requests.RequestException: If request fails after retries
        """
        url = f"{self.base_url}/signal"
        self.total_requests += 1

        for attempt in range(self.max_retries):
            try:
                self.logger.debug(f"POST /signal (attempt {attempt + 1}/{self.max_retries})")

                response = self.session.post(
                    url,
                    json=payload,
                    timeout=self.timeout
                )

                # Check for HTTP errors
                response.raise_for_status()

                # Parse response
                data = response.json()
                signal_response = SignalResponse.from_dict(data)

                self.logger.debug(
                    f"Signal: {signal_response.signal}, "
                    f"Confidence: {signal_response.confidence:.3f}, "
                    f"Reason: {signal_response.reason}"
                )

                return signal_response

            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")

                if attempt < self.max_retries - 1:
                    # Retry with exponential backoff
                    delay = self.retry_delay * (2 ** attempt)
                    self.logger.debug(f"Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    self.total_retry_count += 1
                else:
                    # Max retries reached
                    self.failed_requests += 1
                    self.logger.error(f"Request failed after {self.max_retries} attempts")
                    raise

        # Should never reach here, but for type safety
        raise RuntimeError("Unexpected code path in _request")

    def get_stats(self) -> dict:
        """Get client statistics.

        Returns:
            Dictionary with total_requests, failed_requests, total_retry_count
        """
        return {
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "total_retry_count": self.total_retry_count,
            "success_rate": (self.total_requests - self.failed_requests) / max(self.total_requests, 1)
        }

    def close(self):
        """Close the HTTP session and release resources."""
        self.session.close()
