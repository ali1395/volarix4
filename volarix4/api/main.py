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
from volarix4.utils.helpers import calculate_pip_value
from volarix4.config import SR_CONFIG, REJECTION_CONFIG, RISK_CONFIG
from volarix4.utils.logger import setup_logger, log_signal_details
from volarix4.utils.monitor import monitor

# Initialize logger
logger = setup_logger("volarix4", level="INFO")


class OHLCVBar(BaseModel):
    """OHLCV bar data"""
    time: int  # Unix timestamp
    open: float
    high: float
    low: float
    close: float
    volume: int


class SignalRequest(BaseModel):
    """Request schema matching Volarix 3 API exactly"""
    symbol: str
    timeframe: str
    data: list[OHLCVBar]  # OHLCV bars for execution timeframe
    execution_timeframe: str | None = None  # Optional execution TF
    context_timeframe: str | None = None  # Optional context TF (multi-TF)
    context_data: list[OHLCVBar] | None = None  # Context TF bars
    model_type: str = "ensemble"  # Model type (ignored in V4)


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
        """Initialize MT5 connection on startup"""
        logger.info("Starting Volarix 4 API...")
        logger.info("MT5 connection will be established on first request")

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
            # Determine effective timeframe
            exec_tf = request.execution_timeframe or request.timeframe
            ctx_tf = request.context_timeframe
            exec_bar_count = len(request.data)
            ctx_bar_count = len(request.context_data) if request.context_data else 0

            # Determine mode (single-TF vs multi-TF)
            if ctx_tf and ctx_bar_count > 0:
                mode = "Multi-TF (FALLBACK to single-TF - Volarix 4 uses single-TF only)"
                logger.warning(
                    f"Multi-TF requested (ctx_tf={ctx_tf}) but Volarix 4 only supports single-TF. "
                    f"Context data will be ignored. Use Volarix 3 for multi-TF support."
                )
            else:
                mode = "Single-TF"

            # Log request (matching Volarix 3 format)
            logger.info(
                f"Signal request: {request.symbol} [{mode}] | "
                f"Fields: tf={request.timeframe}, exec_tf={request.execution_timeframe}, ctx_tf={request.context_timeframe} | "
                f"Using: exec={exec_tf}, ctx={ctx_tf or 'None'} | "
                f"Bars: exec={exec_bar_count}, ctx={ctx_bar_count} | "
                f"Model: {request.model_type} (ignored - using S/R bounce)"
            )

            # 1. Convert OHLCV data to DataFrame
            # DEBUG: Log bars to check for data corruption
            if len(request.data) > 0:
                first_bar = request.data[0]
                last_bar = request.data[-1]
                logger.info(f"[DEBUG] Total bars received: {len(request.data)}")
                logger.info(f"[DEBUG] First bar [0]: time={first_bar.time}, open={first_bar.open:.5f}, close={first_bar.close:.5f}")

                # Check how many bars are zeros
                zero_count = sum(1 for bar in request.data if bar.time == 0)
                logger.info(f"[DEBUG] Bars with time=0: {zero_count} out of {len(request.data)}")

                # Log a few bars to see the pattern
                if len(request.data) >= 5:
                    for i in [0, 1, 2, len(request.data)-2, len(request.data)-1]:
                        bar = request.data[i]
                        logger.info(f"[DEBUG] Bar [{i}]: time={bar.time}, open={bar.open:.5f}, close={bar.close:.5f}")

                logger.info(f"[DEBUG] Last bar [{len(request.data)-1}]: time={last_bar.time}, open={last_bar.open:.5f}, close={last_bar.close:.5f}")

            df = pd.DataFrame([{
                'time': pd.to_datetime(bar.time, unit='s'),
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume
            } for bar in request.data])

            # DEBUG: Log converted timestamps
            logger.info(f"[DEBUG] First timestamp after conversion: {df['time'].iloc[0]}")
            logger.info(f"[DEBUG] Last timestamp after conversion: {df['time'].iloc[-1]}")

            log_signal_details(logger, "DATA_FETCH", {
                'bars_count': len(df),
                'start_date': str(df['time'].iloc[0]),
                'end_date': str(df['time'].iloc[-1])
            })

            # 2. Session filter (check if latest bar is in valid session)
            last_bar_time = df.iloc[-1]['time']
            session_valid = is_valid_session(last_bar_time)
            log_signal_details(logger, "SESSION_CHECK", {
                'valid': session_valid,
                'timestamp': str(last_bar_time)
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

            # 3. Detect S/R levels
            pip_value = calculate_pip_value(request.symbol)
            levels = detect_sr_levels(
                df,
                min_score=SR_CONFIG["min_level_score"],
                pip_value=pip_value
            )
            log_signal_details(logger, "SR_DETECTION", {
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

            # 4. Find rejection candles
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

            # 5. Calculate trade setup
            trade_setup = calculate_trade_setup(
                rejection,
                sl_pips_beyond=RISK_CONFIG["sl_pips_beyond"],
                tp_ratios=[RISK_CONFIG["tp1_r"], RISK_CONFIG["tp2_r"], RISK_CONFIG["tp3_r"]],
                tp_percents=[RISK_CONFIG["tp1_percent"], RISK_CONFIG["tp2_percent"], RISK_CONFIG["tp3_percent"]],
                pip_value=pip_value
            )

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

            # Record performance metrics
            duration = time.time() - start_time
            monitor.record_request(
                duration=duration,
                signal=trade_setup['signal'],
                success=True,
                symbol=request.symbol,
                confidence=trade_setup['confidence']
            )

            # 6. Return response
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

    return app


# Create the app instance
app = create_app()


def get_app() -> FastAPI:
    """Get the FastAPI application instance."""
    return app
