"""Startup script for Volarix 4 API"""

import uvicorn
from config import API_HOST, API_PORT, DEBUG

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
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info"
    )
