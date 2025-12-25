"""Volarix 4 - Minimal S/R Bounce Trading API"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Literal

# Module imports (to be implemented)
# from data import fetch_mt5_data
# from sr_levels import detect_levels
# from rejection import find_rejection
# from trade_setup import calculate_trade

app = FastAPI(title="Volarix 4", version="4.0.0")


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


@app.post("/signal", response_model=SignalResponse)
async def get_signal(request: SignalRequest) -> SignalResponse:
    """
    Main endpoint for trade signal generation.

    Pipeline:
        1. Fetch OHLC data from MT5
        2. Detect S/R levels
        3. Find rejection candles at levels
        4. Calculate trade setup (SL/TP)
        5. Return signal

    For now, returns dummy response for testing.
    """
    # TODO: Implement full pipeline
    # df = fetch_mt5_data(request.symbol, request.timeframe, request.bars)
    # levels = detect_levels(df)
    # rejection = find_rejection(df, levels)
    # if rejection:
    #     trade = calculate_trade(rejection, rejection['level'], df.iloc[-1]['close'])
    #     return SignalResponse(**trade)

    # Dummy response for skeleton testing
    return SignalResponse(
        signal="HOLD",
        confidence=0.0,
        entry=0.0,
        sl=0.0,
        tp1=0.0,
        tp2=0.0,
        tp3=0.0,
        tp1_percent=0.4,
        tp2_percent=0.4,
        tp3_percent=0.2,
        reason="Skeleton mode - modules not yet implemented"
    )


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "online", "version": "4.0.0", "mode": "skeleton"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
