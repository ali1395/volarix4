"""Logging system for Volarix 4"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any


def setup_logger(name: str = "volarix4", log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    """
    Setup logger with file and console handlers.

    Log format: [TIMESTAMP] [LEVEL] [MODULE] Message
    Logs to: logs/volarix4_YYYY-MM-DD.log

    Args:
        name: Logger name
        log_dir: Directory for log files
        level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger(name)
    # logger.setLevel(getattr(logging, level.upper()))
    logger.setLevel("ERROR")  # Set to ERROR to capture all logs in file

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Create formatte
    detailed_formatter = logging.Formatter(
        fmt='[%(asctime)s] [%(levelname)8s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        fmt='[%(levelname)s] %(message)s'
    )

    # File handler (detailed logs)
    log_file = log_path / f"volarix4_{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # Console handler (simple logs)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(simple_formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def log_signal_details(logger: logging.Logger, step: str, data: Dict[str, Any]):
    """
    Log signal generation step with details.

    Steps:
    - DATA_FETCH: Log bars fetched
    - SR_DETECTION: Log S/R levels found
    - REJECTION_FOUND: Log rejection pattern
    - TRADE_SETUP: Log SL/TP calculation
    - FINAL_SIGNAL: Log final signal output
    - ERROR: Log error details

    Args:
        logger: Logger instance
        step: Step name
        data: Step-specific data dictionary
    """
    if step == "REQUEST":
        logger.info(f"=== NEW REQUEST ===")
        logger.info(f"Symbol: {data.get('symbol')}, Timeframe: {data.get('timeframe')}, Bars: {data.get('bars')}")

    elif step == "DATA_FETCH":
        logger.info(f"Data Fetched: {data.get('bars_count')} bars")
        logger.debug(f"Date Range: {data.get('start_date')} to {data.get('end_date')}")

    elif step == "SESSION_CHECK":
        valid = data.get('valid', False)
        timestamp = data.get('timestamp')
        if valid:
            logger.info(f"Session Check: VALID ({timestamp})")
        else:
            logger.info(f"Session Check: INVALID - Outside London/NY hours ({timestamp})")

    elif step == "SR_DETECTION":
        levels_count = data.get('levels_count', 0)
        logger.info(f"S/R Levels Detected: {levels_count}")

        if levels_count > 0 and data.get('levels'):
            logger.debug("Top S/R Levels:")
            for i, level in enumerate(data['levels'][:3], 1):
                logger.debug(f"  {i}. {level['type'].upper()}: {level['level']:.5f} (score: {level['score']})")

    elif step == "REJECTION_SEARCH":
        found = data.get('found', False)
        if found:
            logger.info(f"Rejection Found: {data.get('direction')} at {data.get('level'):.5f}")
            logger.debug(f"  Level Score: {data.get('level_score')}")
            logger.debug(f"  Confidence: {data.get('confidence')}")
        else:
            logger.info("Rejection Search: No pattern found")

    elif step == "TRADE_SETUP":
        logger.info(f"Trade Setup Calculated:")
        logger.info(f"  Direction: {data.get('direction')}")
        logger.info(f"  Entry: {data.get('entry'):.5f}")
        logger.info(f"  SL: {data.get('sl'):.5f} ({data.get('sl_pips', 0):.1f} pips)")
        logger.info(f"  TP1: {data.get('tp1'):.5f} (40%)")
        logger.info(f"  TP2: {data.get('tp2'):.5f} (40%)")
        logger.info(f"  TP3: {data.get('tp3'):.5f} (20%)")

    elif step == "FINAL_SIGNAL":
        signal = data.get('signal')
        confidence = data.get('confidence', 0)
        reason = data.get('reason', '')

        if signal == "HOLD":
            logger.info(f"Final Signal: HOLD (Reason: {reason})")
        else:
            logger.info(f"Final Signal: {signal} (Confidence: {confidence:.2f})")
            logger.info(f"Reason: {reason}")
        logger.info(f"=== REQUEST COMPLETE ===\n")

    elif step == "ERROR":
        error_msg = data.get('error', 'Unknown error')
        logger.error(f"Error during signal generation: {error_msg}", exc_info=data.get('exc_info'))
        logger.info(f"=== REQUEST FAILED ===\n")


# Test code
if __name__ == "__main__":
    print("Testing logger.py module...\n")

    # Setup logger
    logger = setup_logger(level="DEBUG")

    # Test different log levels
    print("1. Testing log levels:")
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

    # Test signal logging
    print("\n2. Testing signal detail logging:")

    log_signal_details(logger, "REQUEST", {
        'symbol': 'EURUSD',
        'timeframe': 'H1',
        'bars': 400
    })

    log_signal_details(logger, "DATA_FETCH", {
        'bars_count': 400,
        'start_date': '2024-01-01 00:00',
        'end_date': '2024-01-03 02:00'
    })

    log_signal_details(logger, "SESSION_CHECK", {
        'valid': True,
        'timestamp': '2024-01-03 09:00 EST'
    })

    log_signal_details(logger, "SR_DETECTION", {
        'levels_count': 3,
        'levels': [
            {'level': 1.08500, 'score': 85.0, 'type': 'support'},
            {'level': 1.09000, 'score': 70.0, 'type': 'resistance'},
            {'level': 1.08250, 'score': 65.0, 'type': 'support'}
        ]
    })

    log_signal_details(logger, "REJECTION_SEARCH", {
        'found': True,
        'direction': 'BUY',
        'level': 1.08500,
        'level_score': 85.0,
        'confidence': 0.75
    })

    log_signal_details(logger, "TRADE_SETUP", {
        'direction': 'BUY',
        'entry': 1.08520,
        'sl': 1.08390,
        'tp1': 1.08650,
        'tp2': 1.08780,
        'tp3': 1.08910,
        'sl_pips': 13.0
    })

    log_signal_details(logger, "FINAL_SIGNAL", {
        'signal': 'BUY',
        'confidence': 0.75,
        'reason': 'Support bounce at 1.08500, score 85.0'
    })

    print("\n3. Check logs directory for detailed file logs")
    print(f"   Log file: logs/volarix4_{datetime.now().strftime('%Y-%m-%d')}.log")
