"""Trade setup calculation module (SL/TP)"""

from typing import Dict


def calculate_sl_tp(entry: float, level: float, direction: str,
                    sl_pips_beyond: float = 10.0,
                    tp_ratios: list = None,
                    pip_value: float = 0.0001) -> Dict:
    """
    Calculate SL and TP levels based on risk management rules.

    Args:
        entry: Entry price
        level: S/R level price
        direction: 'BUY' or 'SELL'
        sl_pips_beyond: Pips to place SL beyond level
        tp_ratios: List of R multiples for TPs (default: [1, 2, 3])
        pip_value: Value of 1 pip

    Returns:
        Dict with SL, TP1-3, risk pips, and RR ratio
    """
    if tp_ratios is None:
        tp_ratios = [1.0, 2.0, 3.0]

    sl_distance = sl_pips_beyond * pip_value

    if direction == 'BUY':
        # SL below support level
        sl = level - sl_distance
        risk_pips = (entry - sl) / pip_value

        # Calculate TPs (above entry)
        tp1 = entry + (tp_ratios[0] * (entry - sl))
        tp2 = entry + (tp_ratios[1] * (entry - sl))
        tp3 = entry + (tp_ratios[2] * (entry - sl))

    else:  # SELL
        # SL above resistance level
        sl = level + sl_distance
        risk_pips = (sl - entry) / pip_value

        # Calculate TPs (below entry)
        tp1 = entry - (tp_ratios[0] * (sl - entry))
        tp2 = entry - (tp_ratios[1] * (sl - entry))
        tp3 = entry - (tp_ratios[2] * (sl - entry))

    # Calculate risk:reward ratio (using TP2 as reference)
    reward = abs(tp2 - entry) / pip_value
    risk_reward = reward / risk_pips if risk_pips > 0 else 0

    return {
        'sl': round(sl, 5),
        'tp1': round(tp1, 5),
        'tp2': round(tp2, 5),
        'tp3': round(tp3, 5),
        'sl_pips': round(risk_pips, 1),
        'risk_reward': round(risk_reward, 2)
    }


def format_signal_response(rejection: Dict, trade_params: Dict,
                          tp_percents: list = None) -> Dict:
    """
    Format the final API response matching Volarix 3 spec.

    Args:
        rejection: Rejection dict from find_rejection_candle()
        trade_params: Trade params from calculate_sl_tp()
        tp_percents: Position size percentages for each TP

    Returns:
        Complete signal response dict
    """
    if tp_percents is None:
        tp_percents = [0.4, 0.4, 0.2]

    # Build reason string
    level_type = "support" if rejection['direction'] == 'BUY' else "resistance"
    reason = f"{level_type.capitalize()} bounce at {rejection['level']:.5f}, " \
             f"score {rejection['level_score']}"

    return {
        'signal': rejection['direction'],
        'confidence': rejection['confidence'],
        'entry': rejection['entry'],
        'sl': trade_params['sl'],
        'tp1': trade_params['tp1'],
        'tp2': trade_params['tp2'],
        'tp3': trade_params['tp3'],
        'tp1_percent': tp_percents[0],
        'tp2_percent': tp_percents[1],
        'tp3_percent': tp_percents[2],
        'reason': reason
    }


def calculate_trade_setup(rejection: Dict, sl_pips_beyond: float = 10.0,
                         tp_ratios: list = None, tp_percents: list = None,
                         pip_value: float = 0.0001) -> Dict:
    """
    Complete trade setup calculation (main function).

    Args:
        rejection: Rejection dict from find_rejection_candle()
        sl_pips_beyond: Pips to place SL beyond S/R level
        tp_ratios: R multiples for TPs
        tp_percents: Position percentages for each TP
        pip_value: Value of 1 pip

    Returns:
        Complete trade setup matching API response format
    """
    if tp_ratios is None:
        tp_ratios = [1.0, 2.0, 3.0]
    if tp_percents is None:
        tp_percents = [0.4, 0.4, 0.2]

    # Calculate SL/TP levels
    trade_params = calculate_sl_tp(
        entry=rejection['entry'],
        level=rejection['level'],
        direction=rejection['direction'],
        sl_pips_beyond=sl_pips_beyond,
        tp_ratios=tp_ratios,
        pip_value=pip_value
    )

    # Format response
    response = format_signal_response(
        rejection=rejection,
        trade_params=trade_params,
        tp_percents=tp_percents
    )

    return response


# Test code
if __name__ == "__main__":
    print("Testing trade_setup.py module...")

    # Test 1: BUY signal
    print("\n1. Testing BUY trade setup...")
    buy_rejection = {
        'direction': 'BUY',
        'level': 1.08500,
        'level_score': 85.0,
        'entry': 1.08520,
        'candle_index': -1,
        'confidence': 0.75
    }

    buy_setup = calculate_trade_setup(buy_rejection)
    print(f"BUY Signal:")
    print(f"  Entry: {buy_setup['entry']}")
    print(f"  SL: {buy_setup['sl']}")
    print(f"  TP1: {buy_setup['tp1']} ({buy_setup['tp1_percent']*100}%)")
    print(f"  TP2: {buy_setup['tp2']} ({buy_setup['tp2_percent']*100}%)")
    print(f"  TP3: {buy_setup['tp3']} ({buy_setup['tp3_percent']*100}%)")
    print(f"  Confidence: {buy_setup['confidence']}")
    print(f"  Reason: {buy_setup['reason']}")

    # Test 2: SELL signal
    print("\n2. Testing SELL trade setup...")
    sell_rejection = {
        'direction': 'SELL',
        'level': 1.09000,
        'level_score': 70.0,
        'entry': 1.08980,
        'candle_index': -1,
        'confidence': 0.68
    }

    sell_setup = calculate_trade_setup(sell_rejection)
    print(f"SELL Signal:")
    print(f"  Entry: {sell_setup['entry']}")
    print(f"  SL: {sell_setup['sl']}")
    print(f"  TP1: {sell_setup['tp1']} ({sell_setup['tp1_percent']*100}%)")
    print(f"  TP2: {sell_setup['tp2']} ({sell_setup['tp2_percent']*100}%)")
    print(f"  TP3: {sell_setup['tp3']} ({sell_setup['tp3_percent']*100}%)")
    print(f"  Confidence: {sell_setup['confidence']}")
    print(f"  Reason: {sell_setup['reason']}")

    # Test 3: Verify SL/TP distances
    print("\n3. Verifying risk management...")
    pip_value = 0.0001
    buy_risk = (buy_setup['entry'] - buy_setup['sl']) / pip_value
    buy_tp1_reward = (buy_setup['tp1'] - buy_setup['entry']) / pip_value
    buy_tp2_reward = (buy_setup['tp2'] - buy_setup['entry']) / pip_value

    print(f"BUY - Risk: {buy_risk:.1f} pips")
    print(f"BUY - TP1 Reward: {buy_tp1_reward:.1f} pips (1R)")
    print(f"BUY - TP2 Reward: {buy_tp2_reward:.1f} pips (2R)")
    print(f"BUY - Risk:Reward: 1:{buy_tp2_reward/buy_risk:.1f}")
