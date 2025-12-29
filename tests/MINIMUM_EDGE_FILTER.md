# Minimum TP1 Edge After Costs Filter

## Overview

This filter prevents opening trades where TP1 would still result in a loss after accounting for all trading costs. It ensures that even the smallest target (TP1) provides a meaningful profit edge.

## Problem Addressed

**Without this filter:**
- Trades could be opened with TP1 targets that are technically above entry (for BUY) or below entry (for SELL)
- But after accounting for spread, slippage, and commissions, hitting TP1 would still result in a net loss
- Example: Entry at 1.08500, TP1 at 1.08510 (10 pips), but total costs = 12 pips → Loss of 2 pips even if TP1 is hit

**With this filter:**
- Only trades where TP1 provides sufficient edge above costs are opened
- Ensures TP1 exits are actually profitable
- Configurable minimum edge parameter (`min_edge_pips`)

## Implementation

### Location
**File:** `tests/backtest.py`
**Lines:** 864-879 (filter logic), 624 (parameter), 738 (counter), 1168 (display)

### Filter Logic

```python
# Calculate round-trip costs in pips
commission_pips = (2 * commission_per_side_per_lot * lot_size) / usd_per_pip_per_lot
total_cost_pips = spread_pips + (2 * slippage_pips) + commission_pips

# Calculate TP1 distance in pips
if direction == "BUY":
    tp1_distance_pips = (trade_params['tp1'] - actual_entry) / pip_value
else:  # SELL
    tp1_distance_pips = (actual_entry - trade_params['tp1']) / pip_value

# Check minimum edge after costs
if tp1_distance_pips <= total_cost_pips + min_edge_pips:
    # Insufficient edge - TP1 would not be profitable after costs
    filter_rejections["insufficient_edge"] += 1
    signals_generated["HOLD"] += 1
    continue
```

### Cost Calculation Breakdown

**1. Spread Cost:**
```python
spread_pips
```
- Cost of crossing the bid-ask spread
- Paid once at entry (already factored into entry price)

**2. Slippage Cost:**
```python
2 * slippage_pips
```
- Entry slippage + exit slippage
- Accounts for price movement during order execution
- Doubled because it occurs on both entry and exit

**3. Commission Cost:**
```python
commission_pips = (2 * commission_per_side_per_lot * lot_size) / usd_per_pip_per_lot
```
- Entry commission + exit commission
- Converted from USD to pips
- Formula:
  - `commission_per_side_per_lot = $7` (example)
  - `lot_size = 1.0`
  - `usd_per_pip_per_lot = $10`
  - `commission_pips = (2 * 7 * 1.0) / 10 = 1.4 pips`

**4. Total Cost:**
```python
total_cost_pips = spread_pips + (2 * slippage_pips) + commission_pips
```

**Example with default parameters:**
- Spread: 1.0 pips
- Slippage: 2 × 0.5 = 1.0 pips
- Commission: (2 × 7 × 1.0) / 10 = 1.4 pips
- **Total: 3.4 pips**

### TP1 Distance Calculation

**BUY Trade:**
```python
tp1_distance_pips = (trade_params['tp1'] - actual_entry) / pip_value
```
- TP1 is above entry
- Positive distance

**SELL Trade:**
```python
tp1_distance_pips = (actual_entry - trade_params['tp1']) / pip_value
```
- TP1 is below entry
- Positive distance

### Filter Condition

```python
if tp1_distance_pips <= total_cost_pips + min_edge_pips:
    # Reject trade
```

**Requirement:**
```
TP1 distance > Total costs + Minimum edge
```

**With defaults:**
```
TP1 distance > 3.4 + 2.0 = 5.4 pips
```

## Parameters

### `min_edge_pips` (default: 2.0)

**Purpose:** Minimum profit margin above costs required for TP1

**Type:** `float`

**Default:** `2.0` pips

**Meaning:**
- After accounting for all costs, TP1 must provide at least 2.0 pips of profit
- With default costs (3.4 pips), TP1 must be at least 5.4 pips from entry
- Lower values (e.g., 1.0) allow tighter TP1 targets but riskier
- Higher values (e.g., 5.0) ensure more cushion but may reject more trades

**Usage:**
```python
result = run_backtest(
    symbol="EURUSD",
    timeframe="H1",
    min_edge_pips=2.0,  # Default
    # ... other parameters
)
```

## Filter Order

The filter runs in this sequence (from first to last):

1. **Confidence Filter** - Checks rejection confidence
2. **Broken Level Filter** - Checks level cooldown
3. **SL/TP Calculation** - Computes SL/TP using actual entry
4. **Geometry Sanity Check** - Validates TP/SL ordering
5. **✅ Minimum Edge Filter** ← NEW (runs here)
6. **Trade Creation** - Opens the trade

**Why this order matters:**
- Edge filter runs AFTER SL/TP calculation (needs trade_params)
- Edge filter runs AFTER geometry check (no point checking edge if geometry is invalid)
- Edge filter runs BEFORE trade creation (prevents unprofitable trades)

## Examples

### Example 1: Trade Accepted ✅

**Parameters:**
- Entry: 1.08500
- TP1: 1.08560 (60 pips)
- Spread: 1.0 pips
- Slippage: 0.5 pips
- Commission: $7/lot, 1.0 lot, $10/pip

**Calculation:**
```
Total costs = 1.0 + (2 × 0.5) + (2 × 7 × 1.0) / 10 = 3.4 pips
TP1 distance = 60 pips
Required = 3.4 + 2.0 = 5.4 pips

60 > 5.4 ✅ PASS
```

**Result:** Trade opened

**TP1 Profit:**
- Gross: 60 pips
- Costs: 3.4 pips
- Net: 56.6 pips ✅

### Example 2: Trade Rejected ❌

**Parameters:**
- Entry: 1.08500
- TP1: 1.08504 (4 pips)
- Spread: 1.0 pips
- Slippage: 0.5 pips
- Commission: $7/lot, 1.0 lot, $10/pip

**Calculation:**
```
Total costs = 1.0 + (2 × 0.5) + (2 × 7 × 1.0) / 10 = 3.4 pips
TP1 distance = 4 pips
Required = 3.4 + 2.0 = 5.4 pips

4 <= 5.4 ❌ FAIL
```

**Result:** Trade rejected, counter incremented

**TP1 Would Result In:**
- Gross: 4 pips
- Costs: 3.4 pips
- Net: 0.6 pips (insufficient edge)

### Example 3: Borderline Case ⚠

**Parameters:**
- Entry: 1.08500
- TP1: 1.08506 (6 pips)
- Spread: 1.0 pips
- Slippage: 0.5 pips
- Commission: $7/lot, 1.0 lot, $10/pip

**Calculation:**
```
Total costs = 1.0 + (2 × 0.5) + (2 × 7 × 1.0) / 10 = 3.4 pips
TP1 distance = 6 pips
Required = 3.4 + 2.0 = 5.4 pips

6 > 5.4 ✅ PASS (barely)
```

**Result:** Trade opened

**TP1 Profit:**
- Gross: 6 pips
- Costs: 3.4 pips
- Net: 2.6 pips (exactly min_edge + 0.6 buffer)

## Output Display

**Filter Statistics:**
```
--- FILTER STATISTICS ---
Confidence rejections                     25
Broken level rejections                   12
Invalid geometry rejections                0
Insufficient edge rejections               8  ← NEW
Signals generated (BUY/SELL)            45/38
```

**Interpretation:**
- 8 trades were rejected because TP1 didn't provide sufficient profit edge
- These trades would have been risky or unprofitable even if TP1 was hit

## Impact on Strategy

### Positive Effects ✅

1. **Eliminates unprofitable TP1 exits**
   - No more "TP1 hit but still lost money"
   - Every TP1 exit guarantees minimum profit

2. **Improves win rate quality**
   - Winning trades have more meaningful profits
   - Reduces "barely profitable" trades

3. **Better risk management**
   - Ensures reward justifies the costs
   - Aligns with minimum risk:reward requirements

### Potential Drawbacks ⚠

1. **Reduces trade frequency**
   - Tighter TP1 setups will be rejected
   - May miss some marginally profitable opportunities

2. **More sensitive to costs**
   - High commission/spread environments reject more trades
   - May need to adjust `min_edge_pips` for different brokers

## Tuning Recommendations

### Conservative (Low Risk)
```python
min_edge_pips=5.0  # Requires 5 pips profit above costs
```
- Only takes high-confidence, high-edge trades
- Lower frequency, higher quality
- Recommended for high-cost brokers

### Moderate (Balanced)
```python
min_edge_pips=2.0  # Default - requires 2 pips profit above costs
```
- Balanced trade-off between quality and quantity
- Good for most strategies
- Recommended starting point

### Aggressive (High Frequency)
```python
min_edge_pips=0.5  # Requires minimal profit above costs
```
- Accepts tighter TP1 targets
- Higher frequency, lower per-trade quality
- Only for very low-cost brokers

## Cost Scenario Examples

### Low-Cost Broker
```python
spread_pips=0.5
commission_per_side_per_lot=3.5
slippage_pips=0.3

Total costs = 0.5 + (2 × 0.3) + (2 × 3.5) / 10 = 1.8 pips
Required TP1 distance (min_edge_pips=2.0) = 3.8 pips
```

### High-Cost Broker
```python
spread_pips=2.0
commission_per_side_per_lot=10.0
slippage_pips=1.0

Total costs = 2.0 + (2 × 1.0) + (2 × 10.0) / 10 = 6.0 pips
Required TP1 distance (min_edge_pips=2.0) = 8.0 pips
```

**Recommendation:** Increase `min_edge_pips` for high-cost brokers to maintain meaningful edge.

## Relationship to Other Filters

### vs. Confidence Filter
- **Confidence:** Filters by signal quality (pattern strength)
- **Edge:** Filters by profit viability (TP1 profitability)
- **Combined:** Only high-confidence AND profitable trades

### vs. Geometry Filter
- **Geometry:** Validates TP/SL ordering (mathematical correctness)
- **Edge:** Validates TP1 profitability (economic viability)
- **Combined:** Geometrically valid AND economically viable

### vs. Broken Level Filter
- **Broken Level:** Avoids recently failed support/resistance
- **Edge:** Ensures sufficient profit potential
- **Combined:** Respects market structure AND profit requirements

## Verification

To verify the filter is working correctly:

1. **Check filter count:**
   ```
   Insufficient edge rejections > 0
   ```
   If zero, all trades had sufficient edge (or parameter is too lenient)

2. **Check TP1 profitability in CSV:**
   ```python
   df = pd.read_csv('./outputs/trades_EURUSD_H1_20251228_143052.csv')

   # Calculate actual TP1 profit if hit
   df['tp1_gross_pips'] = df['tp1_pips']  # Already in pips
   total_costs = spread_pips + (2 * slippage_pips) + commission_pips
   df['tp1_net_pips'] = df['tp1_gross_pips'] - total_costs

   # All TP1 net should be >= min_edge_pips
   assert all(df['tp1_net_pips'] >= min_edge_pips)
   ```

3. **Monitor rejected trades:**
   - If rejection rate is very high (>50%), consider lowering `min_edge_pips`
   - If rejection rate is very low (<5%), edge filter may be redundant

## Summary

**Purpose:** Prevent opening trades where TP1 would be unprofitable after costs

**Mechanism:** Calculates total round-trip costs and requires TP1 to exceed costs by minimum edge

**Formula:** `TP1_distance > spread + 2×slippage + commission + min_edge_pips`

**Default:** Requires 2 pips profit above costs (5.4 pips total with default costs)

**Benefits:**
- ✅ Eliminates unprofitable TP1 exits
- ✅ Improves win quality
- ✅ Better risk management

**Trade-off:**
- ⚠ May reduce trade frequency
- ⚠ More sensitive to broker costs

**Recommendation:** Start with default (2.0 pips), adjust based on broker costs and strategy requirements.
