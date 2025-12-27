"""
API layer for Volarix 4.

This package contains the FastAPI application and route handlers.
"""

from volarix4.api.main import app, get_app

__all__ = ["app", "get_app"]
