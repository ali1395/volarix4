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
from utils import calculate_pip_value, setup_logging
from config import SR_CONFIG, REJECTION_CONFIG, RISK_CONFIG

# Initialize logger
logger = setup_logging("INFO")

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
    try:
        logger.info(f"Processing signal request: {request.symbol} {request.timeframe}")

        # 1. Fetch OHLC data from MT5
        logger.debug("Fetching OHLC data from MT5...")
        df = fetch_ohlc(request.symbol, request.timeframe, request.bars)
        logger.info(f"Fetched {len(df)} bars for {request.symbol}")

        # 2. Session filter (check if latest bar is in valid session)
        last_bar_time = df.iloc[-1]['time']
        if not is_valid_session(last_bar_time):
            logger.info(f"Outside trading session: {last_bar_time}")
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
        logger.debug("Detecting S/R levels...")
        pip_value = calculate_pip_value(request.symbol)
        levels = detect_sr_levels(
            df,
            min_score=SR_CONFIG["min_level_score"],
            pip_value=pip_value
        )
        logger.info(f"Detected {len(levels)} S/R levels")

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
        logger.debug("Searching for rejection patterns...")
        rejection = find_rejection_candle(
            df,
            levels,
            lookback=REJECTION_CONFIG["lookback_candles"],
            pip_value=pip_value
        )

        if not rejection:
            logger.info("No rejection pattern found")
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

        logger.info(f"Rejection found: {rejection['direction']} at {rejection['level']}")

        # 5. Calculate trade setup
        logger.debug("Calculating trade setup...")
        trade_setup = calculate_trade_setup(
            rejection,
            sl_pips_beyond=RISK_CONFIG["sl_pips_beyond"],
            tp_ratios=[RISK_CONFIG["tp1_r"], RISK_CONFIG["tp2_r"], RISK_CONFIG["tp3_r"]],
            tp_percents=[RISK_CONFIG["tp1_percent"], RISK_CONFIG["tp2_percent"], RISK_CONFIG["tp3_percent"]],
            pip_value=pip_value
        )

        logger.info(f"Signal generated: {trade_setup['signal']} with {trade_setup['confidence']} confidence")

        # 6. Return response
        return SignalResponse(**trade_setup)

    except Exception as e:
        logger.error(f"Error processing signal: {str(e)}", exc_info=True)
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
