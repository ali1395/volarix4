"""Startup script for Volarix 4 API"""

import sys
import os

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from volarix4.config import API_HOST, API_PORT, DEBUG

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║                    VOLARIX 4 API                         ║
║            S/R Bounce Trading Signal Generator           ║
╚══════════════════════════════════════════════════════════╝
    """)

    print(f"Starting server on {API_HOST}:{API_PORT}")
    print(f"Debug mode: {DEBUG}")
    print(f"\nAPI Documentation: http://{API_HOST if API_HOST != '0.0.0.0' else 'localhost'}:{API_PORT}/docs")
    print(f"Health Check: http://{API_HOST if API_HOST != '0.0.0.0' else 'localhost'}:{API_PORT}/health\n")

    uvicorn.run(
        "volarix4.api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info"
    )
