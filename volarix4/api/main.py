"""Volarix 4 - Main API Application"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Literal
import MetaTrader5 as mt5
import json
import time
import pandas as pd

# Package imports
from volarix4.core.data import is_valid_session
from volarix4.core.sr_levels import detect_sr_levels
from volarix4.core.rejection import find_rejection_candle
from volarix4.core.trade_setup import calculate_trade_setup
from volarix4.core.trend_filter import detect_trend, validate_signal_with_trend
from volarix4.core.sr_validation import SRLevelValidator
from volarix4.utils.helpers import calculate_pip_value
from volarix4.config import SR_CONFIG, REJECTION_CONFIG, RISK_CONFIG, BACKTEST_PARITY_CONFIG
from volarix4.utils.logger import setup_logger, log_signal_details
from volarix4.utils.monitor import monitor
from volarix4.utils.bar_validation import (
    normalize_and_validate_bars,
    log_bar_validation_summary,
    validate_decision_bar_closed,
    BarValidationError
)

# Initialize logger
logger = setup_logger("volarix4", level="INFO")

# Signal cooldown tracking (symbol -> last signal timestamp)
from datetime import datetime, timedelta
_signal_cooldown_tracker = {}


class OHLCVBar(BaseModel):
    """OHLCV bar data"""
    time: int  # Unix timestamp
    open: float
    high: float
    low: float
    close: float
    volume: int


class SignalRequest(BaseModel):
    """Request schema for Volarix 4 API"""
    symbol: str
    timeframe: str

    # New optimized approach: send only bar timestamp, fetch bars in Python
    bar_time: int | None = None  # Unix timestamp of bar to generate signal for
    lookback_bars: int = 400  # Number of bars to fetch before bar_time

    # Legacy support: accept full bar data (for backward compatibility)
    data: list[OHLCVBar] | None = None  # OHLCV bars for execution timeframe
    execution_timeframe: str | None = None  # Optional execution TF
    context_timeframe: str | None = None  # Optional context TF (multi-TF)
    context_data: list[OHLCVBar] | None = None  # Context TF bars
    model_type: str = "ensemble"  # Model type (ignored in V4)

    # Strategy parameters (optional - for backtest parity with tests/backtest.py)
    min_confidence: float | None = None
    broken_level_cooldown_hours: float | None = None
    broken_level_break_pips: float | None = None
    min_edge_pips: float | None = None

    # Cost model parameters (optional - for backtest parity)
    spread_pips: float | None = None
    slippage_pips: float | None = None
    commission_per_side_per_lot: float | None = None
    usd_per_pip_per_lot: float | None = None
    lot_size: float | None = None


class SignalResponse(BaseModel):
    """Response schema matching Volarix 3"""
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


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Volarix 4",
        version="4.0.0",
        description="S/R Bounce Trading API"
    )

    # Request validation error handler
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle validation errors with detailed logging."""

        # Get request body for logging
        try:
            body = await request.body()
            body_str = body.decode('utf-8')
        except:
            body_str = "Unable to read body"

        # Log detailed error
        logger.error("=" * 70)
        logger.error("REQUEST VALIDATION ERROR (422)")
        logger.error("=" * 70)
        logger.error(f"Endpoint: {request.url.path}")
        logger.error(f"Method: {request.method}")
        logger.error(f"Request Body: {body_str}")
        logger.error(f"\nValidation Errors:")

        for error in exc.errors():
            logger.error(f"  Field: {'.'.join(str(x) for x in error['loc'])}")
            logger.error(f"  Error: {error['msg']}")
            logger.error(f"  Type: {error['type']}")

        logger.error("=" * 70)
        logger.error("\nExpected Format (Volarix 3 Compatible):")
        logger.error(json.dumps({
            "symbol": "EURUSD",
            "timeframe": "H1",
            "data": [
                {
                    "time": 1640000000,
                    "open": 1.08500,
                    "high": 1.08600,
                    "low": 1.08400,
                    "close": 1.08550,
                    "volume": 1000
                }
            ],
            "execution_timeframe": "H1 (optional)",
            "context_timeframe": "H4 (optional - ignored in V4)",
            "context_data": "(optional - ignored in V4)",
            "model_type": "ensemble (optional - ignored in V4)"
        }, indent=2))
        logger.error("=" * 70 + "\n")

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": exc.errors(),
                "body": body_str,
                "expected_format": {
                    "symbol": "string (e.g., EURUSD)",
                    "timeframe": "string (e.g., H1, M15, D1)",
                    "data": "array of OHLCV bars [{time, open, high, low, close, volume}]",
                    "execution_timeframe": "string (optional)",
                    "context_timeframe": "string (optional - ignored in V4)",
                    "context_data": "array (optional - ignored in V4)",
                    "model_type": "string (optional - ignored in V4)"
                }
            }
        )

    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log all incoming requests."""

        # Log incoming request
        logger.info(f">> {request.method} {request.url.path}")

        # Get request body for POST requests
        if request.method == "POST":
            try:
                body = await request.body()
                body_str = body.decode('utf-8')
                logger.debug(f"  Request Body: {body_str}")

                # Reset body for actual handler
                async def receive():
                    return {"type": "http.request", "body": body}
                request._receive = receive

            except Exception as e:
                logger.debug(f"  Could not read body: {e}")

        # Process request
        response = await call_next(request)

        # Log response
        logger.info(f"<< {request.method} {request.url.path} - Status: {response.status_code}")

        return response

    @app.on_event("startup")
    async def startup_event():
        """Initialize MT5 connection and pre-load S/R cache on startup"""
        try:
            print("[STARTUP] Starting Volarix 4 API...", flush=True)
            logger.info("Starting Volarix 4 API...")
            logger.info("MT5 connection will be established on first request")

            # Pre-load S/R levels for common pairs
            logger.info("=" * 70)
            logger.info("PRE-LOADING S/R LEVELS CACHE")
            logger.info("=" * 70)
            print("\n" + "=" * 70)
            print("PRE-LOADING S/R LEVELS CACHE")
            print("=" * 70)

            from volarix4.core.sr_cache import get_sr_cache
            from volarix4.utils.helpers import calculate_pip_value

            cache = get_sr_cache()
            print(f"[STARTUP] Cache instance created: {cache}", flush=True)

            # Pre-load for EURUSD H1 (most common for backtesting)
            # You can add more symbols/timeframes as needed
            symbols_to_cache = [
                ("EURUSD", "H1"),
                # Add more: ("GBPUSD", "H1"), ("USDJPY", "H1"), etc.
            ]

            print(f"Symbols to cache: {symbols_to_cache}", flush=True)

            for symbol, timeframe in symbols_to_cache:
                print(f"\nProcessing {symbol} {timeframe}...", flush=True)
                try:
                    pip_value = calculate_pip_value(symbol)
                    print(f"[STARTUP] Calling cache.preload...", flush=True)
                    cache.preload(
                        symbol=symbol,
                        timeframe=timeframe,
                        years=5,
                        lookback_bars=400,  # Match backtest lookback
                        pip_value=pip_value,
                        min_score=60.0,
                        force_recalculate=True  # FORCE FULL RECALCULATION
                    )
                    print(f"[STARTUP] cache.preload completed for {symbol} {timeframe}", flush=True)
                except Exception as e:
                    error_msg = f"Failed to preload {symbol} {timeframe}: {e}"
                    logger.error(error_msg, exc_info=True)
                    print(f"[STARTUP ERROR] {error_msg}", flush=True)
                    import traceback
                    traceback.print_exc()

            print(f"[STARTUP] Getting cache stats...", flush=True)
            stats = cache.get_cache_stats()
            print(f"[STARTUP] Cache stats: {stats}", flush=True)

            logger.info("=" * 70)
            logger.info("S/R CACHE READY")
            logger.info(f"Cached {stats['cached_pairs']} symbol/timeframe pairs")
            logger.info("=" * 70)

            print("\n" + "=" * 70)
            print("S/R CACHE READY")
            print(f"Cached {stats['cached_pairs']} symbol/timeframe pairs")
            print("=" * 70 + "\n")
            print(flush=True)

            print("[STARTUP] Startup event completing...", flush=True)
            logger.info("Startup event completed successfully")
            print("[STARTUP] ✓ Startup event completed successfully\n", flush=True)

        except Exception as e:
            print(f"[STARTUP FATAL ERROR] {e}", flush=True)
            import traceback
            traceback.print_exc()
            raise

    @app.on_event("shutdown")
    async def shutdown_event():
        """Close MT5 connection on shutdown"""
        logger.info("Shutting down Volarix 4 API...")
        if mt5.terminal_info():
            mt5.shutdown()
            logger.info("MT5 connection closed")

    @app.post("/signal", response_model=SignalResponse)
    async def generate_signal(request: SignalRequest) -> SignalResponse:
        """
        Generate trading signal from OHLCV data.

        This endpoint matches Volarix 3 API for drop-in compatibility.
        Volarix 4 uses pure S/R bounce strategy (no ML models).

        Pipeline:
        1. Convert OHLCV data to DataFrame
        2. Detect S/R levels
        3. Find rejection candles
        4. Calculate trade setup
        5. Return signal

        Args:
            request: SignalRequest with symbol, timeframe, OHLCV bars

        Returns:
            SignalResponse with trading signal and risk parameters
        """
        start_time = time.time()

        try:
            # Resolve strategy parameters (use request values or defaults from BACKTEST_PARITY_CONFIG)
            min_confidence = request.min_confidence if request.min_confidence is not None else BACKTEST_PARITY_CONFIG["min_confidence"]
            broken_level_cooldown_hours = request.broken_level_cooldown_hours if request.broken_level_cooldown_hours is not None else BACKTEST_PARITY_CONFIG["broken_level_cooldown_hours"]
            broken_level_break_pips = request.broken_level_break_pips if request.broken_level_break_pips is not None else BACKTEST_PARITY_CONFIG["broken_level_break_pips"]
            min_edge_pips = request.min_edge_pips if request.min_edge_pips is not None else BACKTEST_PARITY_CONFIG["min_edge_pips"]

            # Resolve cost model parameters
            spread_pips = request.spread_pips if request.spread_pips is not None else BACKTEST_PARITY_CONFIG["spread_pips"]
            slippage_pips = request.slippage_pips if request.slippage_pips is not None else BACKTEST_PARITY_CONFIG["slippage_pips"]
            commission_per_side_per_lot = request.commission_per_side_per_lot if request.commission_per_side_per_lot is not None else BACKTEST_PARITY_CONFIG["commission_per_side_per_lot"]
            usd_per_pip_per_lot = request.usd_per_pip_per_lot if request.usd_per_pip_per_lot is not None else BACKTEST_PARITY_CONFIG["usd_per_pip_per_lot"]
            lot_size = request.lot_size if request.lot_size is not None else BACKTEST_PARITY_CONFIG["lot_size"]

            # Log resolved parameter values for verification
            logger.info("=" * 70)
            logger.info("RESOLVED STRATEGY PARAMETERS (Backtest Parity Mode)")
            logger.info("=" * 70)
            logger.info(f"  min_confidence: {min_confidence}")
            logger.info(f"  broken_level_cooldown_hours: {broken_level_cooldown_hours}")
            logger.info(f"  broken_level_break_pips: {broken_level_break_pips}")
            logger.info(f"  min_edge_pips: {min_edge_pips}")
            logger.info(f"Cost Model Parameters:")
            logger.info(f"  spread_pips: {spread_pips}")
            logger.info(f"  slippage_pips: {slippage_pips}")
            logger.info(f"  commission_per_side_per_lot: ${commission_per_side_per_lot}")
            logger.info(f"  usd_per_pip_per_lot: ${usd_per_pip_per_lot}")
            logger.info(f"  lot_size: {lot_size}")
            logger.info("=" * 70)

            # Determine if we're using the new optimized approach (bar_time) or legacy (data array)
            if request.bar_time is not None:
                # New optimized approach: fetch bars using Python
                logger.info("=" * 70)
                logger.info("OPTIMIZED MODE: Fetching bars from MT5 using Python")
                logger.info("=" * 70)
                logger.info(f"Bar time (Unix): {request.bar_time}")
                logger.info(f"Lookback bars requested: {request.lookback_bars}")

                # Ensure we fetch at least 200 bars (required by parity contract)
                MIN_BARS_REQUIRED = 200
                actual_lookback = max(request.lookback_bars, MIN_BARS_REQUIRED)

                if actual_lookback > request.lookback_bars:
                    logger.warning(f"Lookback bars increased from {request.lookback_bars} to {actual_lookback} (minimum required by parity contract)")

                # Import fetch_ohlc
                from volarix4.core.data import fetch_ohlc

                # Convert Unix timestamp to datetime
                bar_datetime = datetime.fromtimestamp(request.bar_time)
                logger.info(f"Bar datetime: {bar_datetime}")
                logger.info(f"Fetching {actual_lookback} bars before {bar_datetime}")

                # Fetch bars before bar_time (not including it)
                try:
                    df_fetched = fetch_ohlc(
                        symbol=request.symbol,
                        timeframe=request.timeframe,
                        bars=actual_lookback,
                        end_time=bar_datetime
                    )
                    logger.info(f"Successfully fetched {len(df_fetched)} bars from MT5")
                    logger.info(f"First bar: {df_fetched['time'].iloc[0]}")
                    logger.info(f"Last bar: {df_fetched['time'].iloc[-1]}")
                    logger.info(f"Bar we're generating signal for: {bar_datetime} (excluded)")
                    logger.info("=" * 70)

                    # Convert DataFrame back to bars_dict format for validation
                    bars_dict = [{
                        'time': int(row['time'].timestamp()),
                        'open': row['open'],
                        'high': row['high'],
                        'low': row['low'],
                        'close': row['close'],
                        'volume': row['volume']
                    } for _, row in df_fetched.iterrows()]

                    exec_bar_count = len(bars_dict)
                    mode = "Single-TF (Optimized - Python fetch)"

                except Exception as e:
                    logger.error(f"Failed to fetch bars from MT5: {e}")
                    return SignalResponse(
                        signal="HOLD",
                        confidence=0.0,
                        entry=0.0,
                        sl=0.0,
                        tp1=0.0,
                        tp2=0.0,
                        tp3=0.0,
                        tp1_percent=RISK_CONFIG["tp1_percent"],
                        tp2_percent=RISK_CONFIG["tp2_percent"],
                        tp3_percent=RISK_CONFIG["tp3_percent"],
                        reason=f"Failed to fetch bars from MT5: {str(e)}"
                    )

            else:
                # Legacy approach: use provided data array
                if request.data is None or len(request.data) == 0:
                    logger.error("No bar_time or data provided in request")
                    return SignalResponse(
                        signal="HOLD",
                        confidence=0.0,
                        entry=0.0,
                        sl=0.0,
                        tp1=0.0,
                        tp2=0.0,
                        tp3=0.0,
                        tp1_percent=RISK_CONFIG["tp1_percent"],
                        tp2_percent=RISK_CONFIG["tp2_percent"],
                        tp3_percent=RISK_CONFIG["tp3_percent"],
                        reason="No bar_time or data provided in request"
                    )

                logger.info("LEGACY MODE: Using provided bar data")

                # Convert request.data to dict format for validation
                bars_dict = [{
                    'time': bar.time,
                    'open': bar.open,
                    'high': bar.high,
                    'low': bar.low,
                    'close': bar.close,
                    'volume': bar.volume
                } for bar in request.data]

                exec_bar_count = len(bars_dict)
                mode = "Single-TF (Legacy - bars provided)"

            # Determine effective timeframe
            exec_tf = request.execution_timeframe or request.timeframe
            ctx_tf = request.context_timeframe
            ctx_bar_count = len(request.context_data) if request.context_data else 0

            # Check for multi-TF (not supported in V4)
            if ctx_tf and ctx_bar_count > 0:
                logger.warning(
                    f"Multi-TF requested (ctx_tf={ctx_tf}) but Volarix 4 only supports single-TF. "
                    f"Context data will be ignored. Use Volarix 3 for multi-TF support."
                )

            # Log request
            logger.info(
                f"Signal request: {request.symbol} [{mode}] | "
                f"Timeframe: {request.timeframe} | "
                f"Bars: {exec_bar_count} | "
                f"Bar time: {request.bar_time if request.bar_time else 'N/A (legacy mode)'}"
            )

            # 1. Bar Validation (Parity Contract Enforcement)
            # Validate and normalize bars per Parity Contract
            try:
                validated_bars, bar_metadata = normalize_and_validate_bars(
                    bars=bars_dict,
                    timeframe=request.timeframe,
                    min_bars=200,  # Per Parity Contract: exec200 lookback
                    allow_gap_tolerance=True,
                    max_gap_multiplier=168  # 1 week = 168 hours (allows weekends + holidays)
                )
            except BarValidationError as e:
                logger.error(f"Bar validation failed: {e}")
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": "Bar Validation Failed",
                        "message": str(e),
                        "details": "Bars violate Parity Contract. Ensure MT5 EA sends only closed bars with strictly increasing timestamps."
                    }
                )

            # Log validation summary (request echo debug)
            log_bar_validation_summary(
                logger=logger,
                metadata=bar_metadata,
                symbol=request.symbol,
                timeframe=request.timeframe
            )

            # Validate decision bar is closed (not forming)
            current_time = int(time.time())
            validate_decision_bar_closed(
                decision_bar_time=bar_metadata['decision_bar_time'],
                current_time=current_time,
                timeframe_seconds=bar_metadata['timeframe_seconds'],
                logger=logger
            )

            # 2. Convert validated bars to DataFrame
            df = pd.DataFrame([{
                'time': pd.to_datetime(bar['time'], unit='s'),
                'open': bar['open'],
                'high': bar['high'],
                'low': bar['low'],
                'close': bar['close'],
                'volume': bar['volume']
            } for bar in validated_bars])

            log_signal_details(logger, "DATA_FETCH", {
                'bars_count': bar_metadata['bar_count'],
                'start_date': str(bar_metadata['first_datetime']),
                'end_date': str(bar_metadata['last_datetime']),
                'decision_bar_time': str(bar_metadata['decision_datetime']),
                'decision_bar_close': bar_metadata['decision_bar_close']
            })

            # 3. Session filter (check if decision bar is in valid session)
            # Use decision_bar_time from metadata (already validated as closed bar)
            decision_bar_datetime = bar_metadata['decision_datetime']
            session_valid = is_valid_session(decision_bar_datetime)
            log_signal_details(logger, "SESSION_CHECK", {
                'valid': session_valid,
                'timestamp': str(decision_bar_datetime),
                'decision_bar_time': bar_metadata['decision_bar_time']
            })

            if not session_valid:
                return SignalResponse(
                    signal="HOLD",
                    confidence=0.0,
                    entry=0.0,
                    sl=0.0,
                    tp1=0.0,
                    tp2=0.0,
                    tp3=0.0,
                    tp1_percent=RISK_CONFIG["tp1_percent"],
                    tp2_percent=RISK_CONFIG["tp2_percent"],
                    tp3_percent=RISK_CONFIG["tp3_percent"],
                    reason=f"Outside trading session (London/NY only)"
                )

            # 4. Trend Filter (EMA 20/50)
            trend_info = detect_trend(df, ema_fast=20, ema_slow=50)
            log_signal_details(logger, "TREND_FILTER", {
                'trend': trend_info['trend'],
                'strength': trend_info['strength'],
                'allow_buy': trend_info['allow_buy'],
                'allow_sell': trend_info['allow_sell'],
                'reason': trend_info['reason']
            })

            # 5. Detect S/R levels (using cache if available)
            pip_value = calculate_pip_value(request.symbol)

            # Try to get levels from cache first
            from volarix4.core.sr_cache import get_sr_cache
            cache = get_sr_cache()

            # Look up pre-calculated S/R levels for this bar
            levels = cache.get_levels_for_bar(
                symbol=request.symbol,
                timeframe=request.timeframe,
                bar_time=decision_bar_datetime
            )

            # Fall back to real-time calculation if cache miss
            if levels is None:
                logger.warning("Cache miss - calculating S/R levels on-the-fly")
                levels = detect_sr_levels(
                    df,
                    min_score=SR_CONFIG["min_level_score"],
                    pip_value=pip_value
                )
                log_signal_details(logger, "SR_DETECTION", {
                    'source': 'real-time',
                    'levels_count': len(levels),
                    'levels': levels[:5]  # Log top 5
                })
            else:
                log_signal_details(logger, "SR_DETECTION", {
                    'source': 'cache',
                    'levels_count': len(levels),
                    'levels': levels[:5]  # Log top 5
                })

            if not levels:
                logger.info("No significant S/R levels found")
                return SignalResponse(
                    signal="HOLD",
                    confidence=0.0,
                    entry=0.0,
                    sl=0.0,
                    tp1=0.0,
                    tp2=0.0,
                    tp3=0.0,
                    tp1_percent=RISK_CONFIG["tp1_percent"],
                    tp2_percent=RISK_CONFIG["tp2_percent"],
                    tp3_percent=RISK_CONFIG["tp3_percent"],
                    reason="No significant S/R levels detected"
                )

            # 6. Validate S/R levels (filter broken levels)
            logger.info("Checking Broken Level Filter...")
            sr_validator = SRLevelValidator(
                pip_value=pip_value,
                cooldown_hours=broken_level_cooldown_hours,
                invalidation_threshold_pips=broken_level_break_pips
            )
            levels_before = len(levels)

            # Log level details before validation
            logger.info(f"S/R Levels before validation: {levels_before}")
            for i, level_dict in enumerate(levels[:5], 1):  # Log top 5
                logger.info(f"  Level {i}: {level_dict['level']:.5f} ({level_dict['type']}, score: {level_dict['score']:.1f})")

            levels = sr_validator.validate_levels(levels, df)
            levels_after = len(levels)

            broken_info = sr_validator.get_broken_levels_info()
            if broken_info:
                logger.info(f"Broken levels in cooldown: {len(broken_info)}")
                for broken in broken_info:
                    logger.info(f"  - Level {broken['level']:.5f}: Broken {broken['hours_ago']:.1f}h ago, {broken['cooldown_remaining']:.1f}h cooldown remaining")

            log_signal_details(logger, "SR_VALIDATION", {
                'levels_before': levels_before,
                'levels_after': levels_after,
                'broken_levels': broken_info
            })

            if levels_after < levels_before:
                logger.info(f"Broken Level Filter: {levels_before - levels_after} levels filtered out")
            else:
                logger.info(f"Broken Level Filter: PASSED - All levels valid")

            if not levels:
                logger.info("Broken Level Filter: FAILED - All levels broken or in cooldown")
                logger.info("Signal Rejected - Reason: All S/R levels broken or in cooldown period")

                return SignalResponse(
                    signal="HOLD",
                    confidence=0.0,
                    entry=0.0,
                    sl=0.0,
                    tp1=0.0,
                    tp2=0.0,
                    tp3=0.0,
                    tp1_percent=RISK_CONFIG["tp1_percent"],
                    tp2_percent=RISK_CONFIG["tp2_percent"],
                    tp3_percent=RISK_CONFIG["tp3_percent"],
                    reason="All S/R levels broken or in cooldown period"
                )

            logger.info(f"Valid S/R Levels after validation: {levels_after}")

            # 7. Find rejection candles
            rejection = find_rejection_candle(
                df,
                levels,
                lookback=REJECTION_CONFIG["lookback_candles"],
                pip_value=pip_value
            )

            if not rejection:
                log_signal_details(logger, "REJECTION_SEARCH", {'found': False})
                return SignalResponse(
                    signal="HOLD",
                    confidence=0.0,
                    entry=0.0,
                    sl=0.0,
                    tp1=0.0,
                    tp2=0.0,
                    tp3=0.0,
                    tp1_percent=RISK_CONFIG["tp1_percent"],
                    tp2_percent=RISK_CONFIG["tp2_percent"],
                    tp3_percent=RISK_CONFIG["tp3_percent"],
                    reason="No rejection pattern at S/R levels"
                )

            log_signal_details(logger, "REJECTION_SEARCH", {
                'found': True,
                'direction': rejection['direction'],
                'level': rejection['level'],
                'level_score': rejection['level_score'],
                'confidence': rejection['confidence']
            })

            # Detailed rejection pattern logging
            logger.info("=" * 70)
            logger.info(f"Rejection Found [{rejection['direction']}] at {rejection['entry']:.5f} (Level: {rejection['level']:.5f})")

            # Get candle details for logging
            candle_idx = rejection.get('candle_index', -1)
            if candle_idx is not None and candle_idx < 0:
                candle = df.iloc[candle_idx]
                wick_size = candle['high'] - candle['low']
                body_size = abs(candle['close'] - candle['open'])
                wick_body_ratio = wick_size / body_size if body_size > 0 else 0

                logger.info(f"Pattern Details:")
                logger.info(f"  - Candle Index: {candle_idx}")
                logger.info(f"  - Open: {candle['open']:.5f}, High: {candle['high']:.5f}, Low: {candle['low']:.5f}, Close: {candle['close']:.5f}")
                logger.info(f"  - Wick Size: {wick_size / pip_value:.1f} pips")
                logger.info(f"  - Body Size: {body_size / pip_value:.1f} pips")
                logger.info(f"  - Wick/Body Ratio: {wick_body_ratio:.2f}")
                logger.info(f"  - Confidence Score: {rejection['confidence']:.3f}")
                logger.info(f"  - Level Score: {rejection['level_score']:.1f}")
                logger.info(f"  - Distance from Level: {abs(rejection['entry'] - rejection['level']) / pip_value:.1f} pips")
            logger.info("=" * 70)

            # 6.5. Check minimum confidence threshold
            logger.info("Checking Confidence Score...")
            logger.info(f"Rejection Score: {rejection['confidence']:.3f}, Min Required: {min_confidence}")

            if rejection['confidence'] < min_confidence:
                logger.info(f"Confidence Filter: FAILED - Score {rejection['confidence']:.3f} below threshold {min_confidence}")
                logger.info("Signal Rejected - Reason: Confidence too low")

                log_signal_details(logger, "CONFIDENCE_CHECK", {
                    'confidence': rejection['confidence'],
                    'min_required': min_confidence,
                    'passed': False
                })

                return SignalResponse(
                    signal="HOLD",
                    confidence=rejection['confidence'],
                    entry=0.0,
                    sl=0.0,
                    tp1=0.0,
                    tp2=0.0,
                    tp3=0.0,
                    tp1_percent=RISK_CONFIG["tp1_percent"],
                    tp2_percent=RISK_CONFIG["tp2_percent"],
                    tp3_percent=RISK_CONFIG["tp3_percent"],
                    reason=f"Confidence too low ({rejection['confidence']:.2f} < {min_confidence})"
                )

            logger.info(f"Confidence Filter: PASSED")

            log_signal_details(logger, "CONFIDENCE_CHECK", {
                'confidence': rejection['confidence'],
                'min_required': min_confidence,
                'passed': True
            })

            # 8. Validate signal aligns with trend (with exception for high confidence counter-trend)
            logger.info("Checking Trend Filter...")
            current_close = df['close'].iloc[-1]
            logger.info(f"EMA Fast (20): {trend_info['ema_fast']:.5f}, EMA Slow (50): {trend_info['ema_slow']:.5f}")
            logger.info(f"Current Close: {current_close:.5f}, Signal Direction: {rejection['direction']}")
            logger.info(f"Trend: {trend_info['trend']}, Strength: {trend_info['strength']:.3f}")
            logger.info(f"Rejection Confidence: {rejection['confidence']:.3f}, Level Score: {rejection['level_score']:.1f}")

            trend_validation = validate_signal_with_trend(rejection['direction'], trend_info)

            # CRITICAL FIX: Allow counter-trend trades when confidence > 0.85 at strong S/R levels
            high_confidence_override = rejection['confidence'] > 0.75 and rejection['level_score'] >= 80.0

            log_signal_details(logger, "TREND_VALIDATION", {
                'signal_direction': rejection['direction'],
                'valid': trend_validation['valid'],
                'high_confidence_override': high_confidence_override,
                'reason': trend_validation['reason']
            })

            if not trend_validation['valid'] and not high_confidence_override:
                logger.info(f"Trend Filter: FAILED - {trend_validation['reason']}")
                logger.info(f"High Confidence Override: NO (confidence={rejection['confidence']:.3f}, level_score={rejection['level_score']:.1f})")
                logger.info(f"Signal Rejected - Reason: {trend_validation['reason']}")

                return SignalResponse(
                    signal="HOLD",
                    confidence=0.0,
                    entry=0.0,
                    sl=0.0,
                    tp1=0.0,
                    tp2=0.0,
                    tp3=0.0,
                    tp1_percent=RISK_CONFIG["tp1_percent"],
                    tp2_percent=RISK_CONFIG["tp2_percent"],
                    tp3_percent=RISK_CONFIG["tp3_percent"],
                    reason=trend_validation['reason']
                )

            if high_confidence_override and not trend_validation['valid']:
                logger.info(f"Trend Filter: BYPASSED - High confidence counter-trend setup (confidence={rejection['confidence']:.3f} > 0.85, level_score={rejection['level_score']:.1f} >= 80)")
            else:
                logger.info(f"Trend Filter: PASSED - Signal aligns with {trend_info['trend']}")

            # 7.5. Check signal cooldown (4 hours minimum between signals)
            logger.info("Checking Signal Cooldown...")
            cooldown_hours = 2
            # CRITICAL FIX: Use bar timestamp instead of system time for historical data
            current_bar_time = df['time'].iloc[-1]

            if request.symbol in _signal_cooldown_tracker:
                last_signal_time = _signal_cooldown_tracker[request.symbol]
                time_since_last_signal = current_bar_time - last_signal_time

                if time_since_last_signal < timedelta(hours=cooldown_hours):
                    hours_remaining = cooldown_hours - (time_since_last_signal.total_seconds() / 3600)
                    logger.info(f"Last Signal: {last_signal_time}, Current Bar: {current_bar_time}, Hours Since: {time_since_last_signal.total_seconds() / 3600:.1f}h")
                    logger.info(f"Cooldown Filter: FAILED - {hours_remaining:.1f}h remaining in cooldown period")
                    logger.info(f"Signal Rejected - Reason: Signal cooldown active")

                    log_signal_details(logger, "COOLDOWN_CHECK", {
                        'in_cooldown': True,
                        'last_signal': str(last_signal_time),
                        'current_bar': str(current_bar_time),
                        'hours_remaining': round(hours_remaining, 1)
                    })

                    return SignalResponse(
                        signal="HOLD",
                        confidence=0.0,
                        entry=0.0,
                        sl=0.0,
                        tp1=0.0,
                        tp2=0.0,
                        tp3=0.0,
                        tp1_percent=RISK_CONFIG["tp1_percent"],
                        tp2_percent=RISK_CONFIG["tp2_percent"],
                        tp3_percent=RISK_CONFIG["tp3_percent"],
                        reason=f"Signal cooldown active ({hours_remaining:.1f}h remaining)"
                    )

            logger.info(f"Cooldown Filter: PASSED - No recent signals")
            log_signal_details(logger, "COOLDOWN_CHECK", {'in_cooldown': False})

            # 9. Calculate trade setup with risk validation
            logger.info("Calculating Trade Setup and Risk Parameters...")

            trade_setup = calculate_trade_setup(
                rejection,
                sl_pips_beyond=RISK_CONFIG["sl_pips_beyond"],
                tp_ratios=[RISK_CONFIG["tp1_r"], RISK_CONFIG["tp2_r"], RISK_CONFIG["tp3_r"]],
                tp_percents=[RISK_CONFIG["tp1_percent"], RISK_CONFIG["tp2_percent"], RISK_CONFIG["tp3_percent"]],
                pip_value=pip_value,
                max_sl_pips=RISK_CONFIG["max_sl_pips"],
                min_rr=RISK_CONFIG["min_rr"]
            )

            # Check if trade was rejected due to risk parameters
            if trade_setup is None:
                # Calculate SL pips to provide in reason
                sl_distance = abs(rejection['entry'] - (
                    rejection['level'] - (RISK_CONFIG["sl_pips_beyond"] * pip_value)
                    if rejection['direction'] == 'BUY'
                    else rejection['level'] + (RISK_CONFIG["sl_pips_beyond"] * pip_value)
                ))
                sl_pips = sl_distance / pip_value

                logger.info(f"Risk Parameters:")
                logger.info(f"  - Calculated SL: {sl_pips:.1f} pips")
                logger.info(f"  - Max Allowed SL: {RISK_CONFIG['max_sl_pips']:.1f} pips")
                logger.info(f"  - Min Required R:R: {RISK_CONFIG['min_rr']:.1f}")
                logger.info(f"Risk Filter: FAILED - SL exceeds maximum or R:R below minimum")
                logger.info(f"Signal Rejected - Reason: Risk parameters exceeded")

                return SignalResponse(
                    signal="HOLD",
                    confidence=0.0,
                    entry=0.0,
                    sl=0.0,
                    tp1=0.0,
                    tp2=0.0,
                    tp3=0.0,
                    tp1_percent=RISK_CONFIG["tp1_percent"],
                    tp2_percent=RISK_CONFIG["tp2_percent"],
                    tp3_percent=RISK_CONFIG["tp3_percent"],
                    reason=f"Risk parameters exceeded (SL: {sl_pips:.1f} pips, max: {RISK_CONFIG['max_sl_pips']}, min R:R: {RISK_CONFIG['min_rr']})"
                )

            logger.info(f"Risk Filter: PASSED")

            # 8.5. Check minimum edge after costs (backtest parity filter)
            logger.info("Checking Minimum Edge After Costs...")

            # Calculate round-trip costs in pips
            commission_pips = (2 * commission_per_side_per_lot * lot_size) / usd_per_pip_per_lot
            total_cost_pips = spread_pips + (2 * slippage_pips) + commission_pips

            # Calculate TP1 distance in pips
            if trade_setup['signal'] == "BUY":
                tp1_distance_pips = (trade_setup['tp1'] - trade_setup['entry']) / pip_value
            elif trade_setup['signal'] == "SELL":
                tp1_distance_pips = (trade_setup['entry'] - trade_setup['tp1']) / pip_value
            else:
                tp1_distance_pips = 0.0

            logger.info(f"Cost Analysis:")
            logger.info(f"  - Spread: {spread_pips:.1f} pips")
            logger.info(f"  - Slippage (2x): {2 * slippage_pips:.1f} pips")
            logger.info(f"  - Commission: {commission_pips:.2f} pips (${commission_per_side_per_lot} x 2 x {lot_size} lots / ${usd_per_pip_per_lot} per pip)")
            logger.info(f"  - Total Cost: {total_cost_pips:.2f} pips")
            logger.info(f"  - TP1 Distance: {tp1_distance_pips:.2f} pips")
            logger.info(f"  - Min Edge Required: {min_edge_pips:.2f} pips")
            logger.info(f"  - Net Edge: {tp1_distance_pips - total_cost_pips:.2f} pips (need > {min_edge_pips:.2f})")

            # Check if TP1 provides sufficient edge after costs
            if tp1_distance_pips <= total_cost_pips + min_edge_pips:
                logger.info(f"Edge Filter: FAILED - Insufficient edge after costs")
                logger.info(f"Signal Rejected - Reason: TP1 distance ({tp1_distance_pips:.2f} pips) <= total costs ({total_cost_pips:.2f}) + min edge ({min_edge_pips:.2f})")

                log_signal_details(logger, "EDGE_CHECK", {
                    'tp1_distance_pips': round(tp1_distance_pips, 2),
                    'total_cost_pips': round(total_cost_pips, 2),
                    'min_edge_pips': min_edge_pips,
                    'net_edge': round(tp1_distance_pips - total_cost_pips, 2),
                    'passed': False
                })

                return SignalResponse(
                    signal="HOLD",
                    confidence=0.0,
                    entry=0.0,
                    sl=0.0,
                    tp1=0.0,
                    tp2=0.0,
                    tp3=0.0,
                    tp1_percent=RISK_CONFIG["tp1_percent"],
                    tp2_percent=RISK_CONFIG["tp2_percent"],
                    tp3_percent=RISK_CONFIG["tp3_percent"],
                    reason=f"Insufficient edge after costs (TP1: {tp1_distance_pips:.1f} pips, costs: {total_cost_pips:.1f}, min edge: {min_edge_pips:.1f})"
                )

            logger.info(f"Edge Filter: PASSED - Sufficient edge after costs ({tp1_distance_pips - total_cost_pips:.2f} pips > {min_edge_pips:.2f})")

            log_signal_details(logger, "EDGE_CHECK", {
                'tp1_distance_pips': round(tp1_distance_pips, 2),
                'total_cost_pips': round(total_cost_pips, 2),
                'min_edge_pips': min_edge_pips,
                'net_edge': round(tp1_distance_pips - total_cost_pips, 2),
                'passed': True
            })

            log_signal_details(logger, "TRADE_SETUP", {
                'direction': trade_setup['signal'],
                'entry': trade_setup['entry'],
                'sl': trade_setup['sl'],
                'tp1': trade_setup['tp1'],
                'tp2': trade_setup['tp2'],
                'tp3': trade_setup['tp3'],
                'sl_pips': (abs(trade_setup['entry'] - trade_setup['sl']) / pip_value)
            })

            log_signal_details(logger, "FINAL_SIGNAL", {
                'signal': trade_setup['signal'],
                'confidence': trade_setup['confidence'],
                'reason': trade_setup['reason']
            })

            # Final decision logging
            logger.info("=" * 70)
            logger.info("*** ALL FILTERS PASSED - TRADE SIGNAL GENERATED ***")
            logger.info("=" * 70)
            logger.info(f"Signal Direction: {trade_setup['signal']}")
            logger.info(f"Confidence Score: {trade_setup['confidence']:.3f}")
            logger.info(f"Entry Price: {trade_setup['entry']:.5f}")
            logger.info(f"Stop Loss: {trade_setup['sl']:.5f} ({abs(trade_setup['entry'] - trade_setup['sl']) / pip_value:.1f} pips)")
            logger.info(f"Take Profit 1: {trade_setup['tp1']:.5f} ({abs(trade_setup['tp1'] - trade_setup['entry']) / pip_value:.1f} pips, {trade_setup['tp1_percent']*100:.0f}%)")
            logger.info(f"Take Profit 2: {trade_setup['tp2']:.5f} ({abs(trade_setup['tp2'] - trade_setup['entry']) / pip_value:.1f} pips, {trade_setup['tp2_percent']*100:.0f}%)")
            logger.info(f"Take Profit 3: {trade_setup['tp3']:.5f} ({abs(trade_setup['tp3'] - trade_setup['entry']) / pip_value:.1f} pips, {trade_setup['tp3_percent']*100:.0f}%)")
            logger.info(f"Risk:Reward Ratio: 1:{(abs(trade_setup['tp2'] - trade_setup['entry']) / abs(trade_setup['entry'] - trade_setup['sl'])):.2f}")
            logger.info(f"Reason: {trade_setup['reason']}")
            logger.info("=" * 70)
            logger.info(f">>> FINAL SIGNAL: {trade_setup['signal']} <<<")
            logger.info("=" * 70)

            # Update signal cooldown tracker (only for BUY/SELL signals)
            if trade_setup['signal'] in ['BUY', 'SELL']:
                # CRITICAL FIX: Use bar timestamp instead of system time
                _signal_cooldown_tracker[request.symbol] = current_bar_time
                logger.info(f"Signal cooldown activated for {request.symbol} at {current_bar_time} - next signal allowed after {cooldown_hours}h")

            # Record performance metrics
            duration = time.time() - start_time
            monitor.record_request(
                duration=duration,
                signal=trade_setup['signal'],
                success=True,
                symbol=request.symbol,
                confidence=trade_setup['confidence']
            )

            # 10. Return response
            return SignalResponse(**trade_setup)

        except Exception as e:
            log_signal_details(logger, "ERROR", {
                'error': str(e),
                'exc_info': True
            })

            # Record failed request
            duration = time.time() - start_time
            monitor.record_request(
                duration=duration,
                signal="HOLD",
                success=False,
                symbol=request.symbol,
                confidence=0.0
            )

            # Return HOLD signal with error reason
            return SignalResponse(
                signal="HOLD",
                confidence=0.0,
                entry=0.0,
                sl=0.0,
                tp1=0.0,
                tp2=0.0,
                tp3=0.0,
                tp1_percent=RISK_CONFIG["tp1_percent"],
                tp2_percent=RISK_CONFIG["tp2_percent"],
                tp3_percent=RISK_CONFIG["tp3_percent"],
                reason=f"Error: {str(e)}"
            )

        finally:
            # This runs regardless of which return statement executes
            duration = time.time() - start_time
            print(f"[/signal] Request processed in {duration:.3f}s")

    @app.get("/")
    async def root():
        """Root endpoint with API info"""
        return {
            "name": "Volarix 4",
            "version": "4.0.0",
            "status": "online",
            "description": "S/R Bounce Trading API",
            "endpoints": {
                "/signal": "POST - Generate trading signal",
                "/health": "GET - Health check",
                "/docs": "GET - API documentation"
            }
        }

    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        mt5_connected = mt5.terminal_info() is not None

        return {
            "status": "healthy",
            "mt5_connected": mt5_connected,
            "version": "4.0.0"
        }

    @app.get("/cache/stats")
    async def cache_stats():
        """Get S/R cache statistics"""
        from volarix4.core.sr_cache import get_sr_cache
        cache = get_sr_cache()
        return cache.get_cache_stats()

    return app


# Create the app instance
app = create_app()


def get_app() -> FastAPI:
    """Get the FastAPI application instance."""
    return app
