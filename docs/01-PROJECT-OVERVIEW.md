# Volarix 4 - Project Overview

## What is Volarix 4?

Volarix 4 is a **professional trading signal API** that generates BUY/SELL/HOLD signals for forex trading based on **pure price action** using Support and Resistance (S/R) bounce patterns. It's built as a REST API service using FastAPI and integrates with MetaTrader 5 (MT5) for real-time market data access.

## Project Purpose

The primary goal of Volarix 4 is to provide:

1. **Automated Trading Signals**: Generate reliable trading signals without manual chart analysis
2. **API-First Design**: RESTful API that can be consumed by trading bots, Expert Advisors (EAs), or any HTTP client
3. **Rule-Based Strategy**: Pure technical analysis without machine learning (unlike Volarix 3 which used ML)
4. **Drop-in Replacement**: Backward-compatible with Volarix 3 API for seamless migration

## Key Features

### Core Capabilities
- **Real-time Signal Generation**: Analyzes market data and produces actionable trading signals
- **Support/Resistance Detection**: Automatically identifies key S/R levels using swing highs/lows
- **Rejection Pattern Recognition**: Detects pin bars and rejection candles at S/R levels
- **Automated Risk Management**: Calculates entry, stop-loss (SL), and take-profit (TP) levels
- **Session Filtering**: Only trades during London (3-11am EST) and NY (8am-4pm EST) sessions
- **Multi-TP Scaling**: Three take-profit levels (1R, 2R, 3R) with position sizing (40%, 40%, 20%)

### Technical Features
- **FastAPI Framework**: High-performance async API with automatic OpenAPI documentation
- **MT5 Integration**: Direct connection to MetaTrader 5 for live market data
- **Structured Logging**: Comprehensive logging system with daily log rotation
- **Performance Monitoring**: Real-time metrics tracking (response times, signal distribution, etc.)
- **Validation & Error Handling**: Robust input validation and detailed error messages
- **Health Checks**: Built-in health endpoint for monitoring service status

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API Framework** | FastAPI 0.104.1 | REST API server with async support |
| **Web Server** | Uvicorn 0.24.0 | ASGI server for FastAPI |
| **Market Data** | MetaTrader5 | Real-time forex data access |
| **Data Analysis** | Pandas 2.1.3 | Time series data processing |
| **Numerical Computing** | NumPy 1.26.2 | Mathematical operations |
| **Timezone Handling** | pytz 2024.1 | Session time calculations |
| **Configuration** | python-dotenv 1.0.0 | Environment variable management |
| **HTTP Client** | requests 2.31.0 | Testing and integration |

## Project Evolution

**Volarix 4** is the latest iteration in the Volarix series:

- **Volarix 1-2**: Early experimental versions
- **Volarix 3**: Machine learning-based signal generation with multi-timeframe analysis
- **Volarix 4**: Simplified, rule-based approach using pure S/R price action (current version)

### Why the Change from ML to Rule-Based?

Volarix 4 moves away from machine learning for several reasons:
1. **Transparency**: Rule-based logic is easier to understand and debug
2. **Reliability**: No dependency on model training or data quality
3. **Simplicity**: Fewer components, easier deployment and maintenance
4. **Performance**: Faster execution without model inference overhead
5. **Proven Strategy**: S/R bounce patterns are a well-established trading methodology

## Use Cases

### 1. Automated Trading
- Connect to MT5 Expert Advisor (EA) for fully automated trading
- Integration code provided in `mt5_integration/` directory

### 2. Signal Provider Service
- Run as a web service to provide signals to multiple clients
- API-based access for trading bots or applications

### 3. Trading Bot Backend
- Use as the signal engine for a larger trading system
- Combine with position management and risk control systems

### 4. Research & Backtesting
- Analyze historical performance of S/R bounce strategy
- Includes development backtest script (`backtest.py`)

## Project Status

**Current Version**: 4.0.0

**Status**: Production-ready

**Compatibility**: Drop-in replacement for Volarix 3 API

**Maintenance**: Active development

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure MT5 credentials
cp .env.example .env
# Edit .env with your MT5 login details

# 3. Start the API
python start.py

# 4. Test the API
curl http://localhost:8000/health
```

## Next Steps

To understand the project in depth, read the following documentation in order:

1. **Architecture** (`02-ARCHITECTURE.md`) - System design and component structure
2. **Strategy & Logic** (`03-STRATEGY-LOGIC.md`) - Trading strategy implementation details
3. **API Reference** (`04-API-REFERENCE.md`) - Complete API endpoint documentation
4. **Development Guide** (`05-DEVELOPMENT-GUIDE.md`) - How to contribute and extend the project

## License

MIT License - Free to use and modify for personal and commercial purposes.
