"""
Test script for fee calculation implementation.

This script verifies that:
1. calculate_net_spread() works correctly
2. Net spread is properly calculated (Gross - Fees)
3. Fee percentages are accurate
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.metrics import calculate_net_spread


def test_calculate_net_spread():
    """Test the calculate_net_spread function with various scenarios."""
    
    print("=" * 70)
    print("Testing calculate_net_spread() Function")
    print("=" * 70)
    
    # Test Case 1: Positive gross spread, should remain positive after fees
    print("\n📊 Test Case 1: Large Positive Gross Spread")
    gross_spread = 100.0  # $100 spread
    price = 50000.0  # $50,000 BTC price
    fee_bingx = 0.0005  # 0.05%
    fee_bybit = 0.00055  # 0.055%
    
    net_val, net_pct, fee_cost = calculate_net_spread(gross_spread, price, fee_bingx, fee_bybit)
    
    print(f"  Gross Spread: ${gross_spread:.2f}")
    print(f"  Price: ${price:,.2f}")
    print(f"  Fee Rate: {(fee_bingx + fee_bybit) * 100:.3f}%")
    print(f"  Fee Cost: ${fee_cost:.2f}")
    print(f"  Net Spread: ${net_val:.2f} ({net_pct:.3f}%)")
    
    expected_fee = price * (fee_bingx + fee_bybit)
    expected_net = gross_spread - expected_fee
    
    assert abs(fee_cost - expected_fee) < 0.01, f"Fee cost mismatch: {fee_cost} vs {expected_fee}"
    assert abs(net_val - expected_net) < 0.01, f"Net spread mismatch: {net_val} vs {expected_net}"
    print("  ✅ PASS")
    
    # Test Case 2: Small gross spread, becomes negative after fees
    print("\n📊 Test Case 2: Small Gross Spread (Unprofitable)")
    gross_spread = 30.0  # $30 spread
    price = 50000.0
    
    net_val, net_pct, fee_cost = calculate_net_spread(gross_spread, price, fee_bingx, fee_bybit)
    
    print(f"  Gross Spread: ${gross_spread:.2f}")
    print(f"  Fee Cost: ${fee_cost:.2f}")
    print(f"  Net Spread: ${net_val:.2f} ({net_pct:.3f}%)")
    
    if net_val < 0:
        print("  ⚠️  Net spread is NEGATIVE - This trade would be unprofitable!")
    
    assert net_val < 0, "Net spread should be negative for small gross spreads"
    print("  ✅ PASS")
    
    # Test Case 3: Zero gross spread
    print("\n📊 Test Case 3: Zero Gross Spread")
    gross_spread = 0.0
    
    net_val, net_pct, fee_cost = calculate_net_spread(gross_spread, price, fee_bingx, fee_bybit)
    
    print(f"  Gross Spread: ${gross_spread:.2f}")
    print(f"  Fee Cost: ${fee_cost:.2f}")
    print(f"  Net Spread: ${net_val:.2f} ({net_pct:.3f}%)")
    
    assert net_val < 0, "Net spread should be negative when gross is zero"
    print("  ✅ PASS")
    
    # Test Case 4: Breakeven calculation
    print("\n📊 Test Case 4: Breakeven Gross Spread")
    # Calculate minimum gross spread needed to break even
    breakeven_gross = price * (fee_bingx + fee_bybit)
    
    net_val, net_pct, fee_cost = calculate_net_spread(breakeven_gross, price, fee_bingx, fee_bybit)
    
    print(f"  Minimum Gross Spread for Breakeven: ${breakeven_gross:.2f}")
    print(f"  Fee Cost: ${fee_cost:.2f}")
    print(f"  Net Spread: ${net_val:.2f} ({net_pct:.6f}%)")
    
    assert abs(net_val) < 0.01, "Net spread should be ~0 at breakeven"
    print("  ✅ PASS")
    
    # Summary
    print("\n" + "=" * 70)
    print("📈 Fee Calculation Summary")
    print("=" * 70)
    print(f"  Total Fee Rate: {(fee_bingx + fee_bybit) * 100:.3f}%")
    print(f"  Minimum Gross Spread for Profit (at $50k): ${breakeven_gross:.2f}")
    print(f"  Minimum Gross Spread %: {(breakeven_gross / price) * 100:.3f}%")
    print("\n✅ All tests passed! Fee calculation is working correctly.")
    print("=" * 70)


if __name__ == '__main__':
    test_calculate_net_spread()
