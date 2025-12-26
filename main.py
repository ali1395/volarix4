"""Volarix 4 - Minimal S/R Bounce Trading API"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal
import MetaTrader5 as mt5

# Module imports
from data import fetch_ohlc, is_valid_session
from sr_levels import detect_sr_levels
from rejection import find_rejection_candle
from trade_setup import calculate_trade_setup
from utils import calculate_pip_value
from config import SR_CONFIG, REJECTION_CONFIG, RISK_CONFIG
from logger import setup_logger, log_signal_details
from monitor import monitor
import time

# Initialize logger
logger = setup_logger("volarix4", level="INFO")

app = FastAPI(title="Volarix 4", version="4.0.0", description="S/R Bounce Trading API")


class SignalRequest(BaseModel):
    """Request schema matching Volarix 3"""
    symbol: str
    timeframe: str
    bars: int


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
    Generate trading signal based on S/R bounce strategy.

    Pipeline:
    1. Fetch OHLC data from MT5
    2. Detect S/R levels
    3. Find rejection candles
    4. Calculate trade setup
    5. Return signal

    Args:
        request: Signal request with symbol, timeframe, bars

    Returns:
        Signal response with trade setup or HOLD
    """
    start_time = time.time()

    try:
        # Log request
        log_signal_details(logger, "REQUEST", {
            'symbol': request.symbol,
            'timeframe': request.timeframe,
            'bars': request.bars
        })

        # 1. Fetch OHLC data from MT5
        df = fetch_ohlc(request.symbol, request.timeframe, request.bars)
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


if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT, DEBUG

    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level="debug" if DEBUG else "info"
    )
