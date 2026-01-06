# CRITICAL FIX: Z-Score Calculation Logic

## Problem Identified

**Root Cause**: Data mismatch in Z-Score calculation
- History buffer contained NET spreads (after fees)
- Current value used GROSS spread
- This created artificial delta equal to fees (~$52.50)
- Result: Fake Z-Score of 27+ instead of realistic values

## Solution Implemented

### 1. Z-Score Now Uses GROSS Spreads Only

**Before (WRONG)**:
```python
# History: NET spreads
# Current: NET spread
# Problem: Comparing apples to oranges
z_score = (net_spread - net_mean) / net_std
```

**After (CORRECT)**:
```python
# History: GROSS spreads (market data)
# Current: GROSS spread (market data)
# Z-Score measures pure market anomaly
z_score = (gross_spread - gross_mean) / gross_std
```

### 2. Separate Profitability Check

Net spread is calculated separately and used ONLY for profitability validation.

### 3. Dual-Condition Signal Logic

**Entry Signal requires BOTH**:
- ✅ Condition A: `abs(z_score) > threshold` (Market is abnormal)
- ✅ Condition B: `net_spread_pct > 0` (Trade is profitable after fees)

**New Behavior**:
- High Z-Score + Positive Net Spread → **SIGNAL** 🔔
- High Z-Score + Negative Net Spread → **WARNING** ⚠️ (logged, no signal)
- Low Z-Score → **NORMAL** (no action)

## Files Modified

1. `services/live_monitor.py`:
   - `_preload_history()` - stores GROSS spreads
   - `_check_arbitrage_opportunity()` - calculates Z-Score on GROSS
   - `_check_signals()` - dual-condition logic
   - `get_current_stats()` - fixed Z-Score calculation

## Expected Result

After restart:
- Z-Score should be in realistic range (-5 to +5 typically)
- No signals on unprofitable spreads (Net % < 0)
- Warnings logged when Z-Score high but unprofitable

## Action Required

**Restart the application** to reload historical data with GROSS spreads:
```bash
# Stop current process (Ctrl+C)
python3 main.py gui
```
