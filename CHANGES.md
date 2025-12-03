# Summary of Changes

## Files Modified

1. **config/config.yaml** - Added fees configuration
2. **utils/metrics.py** - Added calculate_net_spread() and enhanced calculate_spread_stats()
3. **services/live_monitor.py** - Updated to use net spread for Z-Score calculation
4. **gui/widgets/monitor_table.py** - Updated GUI to display gross, fee, and net spread

## Files Created

1. **test_fee_calculation.py** - Unit tests for fee calculations

## Key Changes

- Z-Score now calculated on **Net Spread** (Gross - Fees) instead of Gross Spread
- Historical baseline stores net spreads, not gross spreads
- GUI displays 8 columns: Symbol, BingX Price, Bybit Price, Gross %, Fee %, Net %, Z-Score, Status
- Net % column color-coded: green for profit, red for loss

## Verification

✅ All unit tests pass
✅ Fee calculation accuracy confirmed
✅ Minimum breakeven spread: 0.105% ($52.50 at $50k BTC)
