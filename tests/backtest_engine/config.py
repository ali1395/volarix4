"""Configuration enums for backtest engine behavior

Defines switches to control exit semantics and TP models for:
- Legacy parity testing (matching bar-based backtest)
- MT5-realistic simulation (true "Open prices only" mode)
"""

from enum import Enum


class ExitSemantics(Enum):
    """How SL/TP hits are evaluated

    OPEN_ONLY: True MT5 "Open prices only" mode
        - Evaluate SL/TP only at bar open price
        - One tick per bar, no intrabar granularity
        - Trade cannot open and close on same bar (unless immediate fill at open)
        - Most conservative simulation

    OHLC_INTRABAR: Legacy hybrid mode
        - Evaluate SL/TP using bar's high/low prices
        - Allows same-bar entry and exit
        - Matches legacy bar-based backtest behavior
        - More optimistic (can catch intrabar moves)
    """
    OPEN_ONLY = "open_only"
    OHLC_INTRABAR = "ohlc_intrabar"


class TPModel(Enum):
    """How take-profit exits are handled

    FULL_CLOSE_AT_FIRST_TP: Legacy parity mode
        - Close 100% of position at first TP hit
        - Simpler accounting (one trade = one deal)
        - Matches legacy bar-based backtest

    PARTIAL_TPS: MT5 realistic mode
        - Close 50% at TP1, 30% at TP2, 20% at TP3
        - One trade creates multiple deals
        - Matches MT5 Strategy Tester behavior
        - Trade "closed" only when position size = 0
    """
    FULL_CLOSE_AT_FIRST_TP = "full_close_first_tp"
    PARTIAL_TPS = "partial_tps"


# Configuration presets
LEGACY_PARITY_CONFIG = {
    'exit_semantics': ExitSemantics.OHLC_INTRABAR,
    'tp_model': TPModel.FULL_CLOSE_AT_FIRST_TP,
    'description': 'Legacy parity mode - matches bar-based backtest'
}

MT5_REALISTIC_CONFIG = {
    'exit_semantics': ExitSemantics.OPEN_ONLY,
    'tp_model': TPModel.PARTIAL_TPS,
    'description': 'MT5 realistic mode - true "Open prices only" simulation'
}

# Default: Use legacy parity for validation
DEFAULT_CONFIG = LEGACY_PARITY_CONFIG


def get_tp_allocations(tp_model: TPModel) -> dict:
    """Get TP allocation percentages for a given model

    Args:
        tp_model: TP model to use

    Returns:
        Dict mapping TP level (1,2,3) to allocation percentage (0.0-1.0)
    """
    if tp_model == TPModel.FULL_CLOSE_AT_FIRST_TP:
        return {1: 1.0, 2: 1.0, 3: 1.0}  # 100% at first TP
    elif tp_model == TPModel.PARTIAL_TPS:
        return {1: 0.5, 2: 0.3, 3: 0.2}  # 50%/30%/20%
    else:
        raise ValueError(f"Unknown TP model: {tp_model}")
