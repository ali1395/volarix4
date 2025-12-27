"""
Volarix 4 - Main Entry Point

Run this file to start the Volarix 4 API server.

Usage:
    python run.py
"""

import uvicorn
from volarix4.config import API_HOST, API_PORT, DEBUG

if __name__ == "__main__":
    uvicorn.run(
        "volarix4.api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info"
    )
