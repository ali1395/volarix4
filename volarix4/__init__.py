"""
Volarix 4 - S/R Bounce Trading API

A professional trading signal API for forex trading based on Support/Resistance
bounce patterns.
"""

__version__ = "4.0.0"
__author__ = "Volarix Development Team"
__license__ = "MIT"

from volarix4.config import (
    SR_CONFIG,
    REJECTION_CONFIG,
    RISK_CONFIG,
    SESSIONS,
    API_HOST,
    API_PORT,
    DEBUG
)

__all__ = [
    "__version__",
    "SR_CONFIG",
    "REJECTION_CONFIG",
    "RISK_CONFIG",
    "SESSIONS",
    "API_HOST",
    "API_PORT",
    "DEBUG"
]
