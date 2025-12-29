# MT5-Style Reporting Logic: Sign-Based vs Status-Based

## The Problem

Previously, the backtest used **status-based categorization**:
- "Winning trade" = hit TP1, TP2, or TP3 (`t.status == "win"`)
- "Losing trade" = hit SL (`t.status == "loss"`)

This caused **misleading metrics** because:
- A trade can hit TP1 but still lose money after costs
- A trade can hit SL but costs are so low it's still slightly profitable

## The Solution

All metrics now use **sign-based categorization**:
- "Profitable deal" = `pnl_after_costs > 0` (actual money made)
- "Loss deal" = `pnl_after_costs < 0` (actual money lost)

This matches **real MT5 Strategy Tester** behavior.

## Example Scenario

### Trade 1: Hits TP1 but Loses Money
```
Entry: 1.10000 (BUY)
TP1:   1.10010 (+10 pips)
Exit:  Hits TP1 → status = "win"

Costs:
  - Spread:     3 pips
  - Slippage:   1 pip (entry) + 1 pip (exit) = 2 pips
  - Commission: 7 pips equivalent
  - Total:      12 pips

PnL Calculation:
  - Gross PnL:         +10 pips (TP1)
  - Entry costs:       -6 pips (spread/2 + slippage + commission)
  - Exit costs:        -6 pips (spread/2 + slippage + commission)
  - Net PnL:           +10 - 12 = -2 pips ❌

Result:
  - Status:            "win" (hit TP1)
  - pnl_after_costs:   -2 pips
  - Sign-based:        LOSS DEAL ✓ (correct)
  - Status-based:      WIN ✗ (misleading)
```

### Trade 2: Hits SL but Makes Money
```
Entry: 1.10000 (BUY)
SL:    1.09995 (-5 pips)
Exit:  Hits SL → status = "loss"

Costs:
  - Spread:     1 pip
  - Slippage:   0.5 pip (entry) + 0.5 pip (exit) = 1 pip
  - Commission: 2 pips equivalent
  - Total:      4 pips

PnL Calculation:
  - Gross PnL:         -5 pips (SL)
  - Entry costs:       -2 pips
  - Exit costs:        -2 pips
  - Net PnL:           -5 - 4 = -9 pips ❌

Result:
  - Status:            "loss" (hit SL)
  - pnl_after_costs:   -9 pips
  - Sign-based:        LOSS DEAL ✓ (correct)
  - Status-based:      LOSS ✓ (correct)
```

**Note:** In practice, hitting SL rarely results in profit, but the example shows the principle.

## Affected Metrics

All these metrics now use sign-based categorization:

1. **Gross Profit/Loss**
   - Before: `sum([t.pnl_after_costs for t in winning_trades])` (status-based)
   - After:  `sum([t.pnl_after_costs for t in profit_deals])` (sign-based)

2. **Win Rate**
   - Before: `(len(winning_trades) / total_trades) * 100` (status-based)
   - After:  `(len(profit_deals) / total_trades) * 100` (sign-based)

3. **Direction Win Rates**
   - Before: `long_wins = [t for t in long_trades if t.status == "win"]`
   - After:  `long_profit_deals = [t for t in long_trades if t.pnl_after_costs > 0]`

4. **Average Win/Loss**
   - Before: Used `winning_trades` and `losing_trades` (status-based)
   - After:  Uses `profit_deals` and `loss_deals` (sign-based)

5. **Largest Win/Loss**
   - Before: Used `winning_trades` and `losing_trades` (status-based)
   - After:  Uses `profit_deals` and `loss_deals` (sign-based)

6. **Consecutive Wins/Losses**
   - Before: `if t.status == "win"` (status-based)
   - After:  `if t.pnl_after_costs > 0` (sign-based)

7. **Walk-Forward Aggregate Metrics**
   - Automatically corrected because they sum per-split metrics
   - Per-split metrics now use sign-based logic

## Code Changes

### Before (Status-Based) ❌
```python
winning_trades = [t for t in completed_trades if t.status == "win"]
losing_trades = [t for t in completed_trades if t.status == "loss"]
win_rate = (len(winning_trades) / total_trades) * 100
gross_profit_pips = sum([t.pnl_after_costs for t in winning_trades])
```

### After (Sign-Based) ✓
```python
# SIGN-BASED CATEGORIZATION (not status-based)
# A trade is "profitable" if pnl_after_costs > 0, regardless of hitting TP
profit_deals = [t for t in completed_trades if t.pnl_after_costs > 0]
loss_deals = [t for t in completed_trades if t.pnl_after_costs < 0]
win_rate = (len(profit_deals) / total_trades) * 100
gross_profit_pips = sum([t.pnl_after_costs for t in profit_deals])
```

## Why This Matters

1. **Accurate Profitability**: Shows true money made/lost, not just TP/SL hits
2. **Matches MT5**: Real MT5 Strategy Tester uses sign-based reporting
3. **Cost-Aware**: High-cost environments (wide spreads, high commissions) properly reflected
4. **Realistic Expectations**: Prevents overestimating strategy performance

## Impact on Results

With high costs (spread=3, commission=7, slippage=2):
- Many TP1 hits (+10 pips) become losers (-2 pips after 12 pip costs)
- Status-based metrics would show inflated win rate
- Sign-based metrics show realistic profitability

**Example:**
- 100 trades, all hit TP1 (+10 pips each)
- Costs: 12 pips per trade
- Net PnL: -2 pips per trade × 100 = -200 pips total

Status-Based Report (WRONG):
```
Win Rate: 100% (all hit TP)
Gross Profit: +1000 pips
Gross Loss: 0 pips
Profit Factor: Inf
→ Looks amazing! ✓ (misleading)
```

Sign-Based Report (CORRECT):
```
Win Rate: 0% (all lost money after costs)
Gross Profit: 0 pips
Gross Loss: 200 pips
Profit Factor: 0.0
→ Strategy is unprofitable ✓ (realistic)
```

## Conclusion

**Sign-based categorization** provides:
- ✓ Accurate profitability metrics
- ✓ Realistic win rates
- ✓ True cost impact visibility
- ✓ MT5-compatible reporting
- ✓ Better strategy evaluation

This ensures you see the **real performance** of your strategy, not just TP/SL hit rates.
