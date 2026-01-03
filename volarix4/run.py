"""
Volarix 4 - Main Entry Point

Run this file to start the Volarix 4 API server.

Usage:
    python run.py
"""

import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import uvicorn
from volarix4.config import API_HOST, API_PORT, DEBUG

if __name__ == "__main__":
    # Determine number of workers based on CPU count
    import os
    import socket
    # TEMPORARY: Disable workers for cache testing
    workers = 1  # os.cpu_count() if not DEBUG else 1

    print(f"Starting API with {workers} worker(s)...")
    print(f"Host: {API_HOST}, Port: {API_PORT}", flush=True)

    # Check if port is available
    try:
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(1)
        result = test_socket.connect_ex((API_HOST if API_HOST != "0.0.0.0" else "127.0.0.1", API_PORT))
        test_socket.close()
        if result == 0:
            print(f"WARNING: Port {API_PORT} appears to be in use!", flush=True)
        else:
            print(f"Port {API_PORT} is available", flush=True)
    except Exception as e:
        print(f"Could not check port: {e}", flush=True)

    print("Starting uvicorn...", flush=True)

    uvicorn.run(
        "volarix4.api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG,
        log_level="info",  # Changed from "error" to see what's happening
        workers=None,  # Disable workers for now - workers incompatible with reload
        timeout_keep_alive=5
    )
