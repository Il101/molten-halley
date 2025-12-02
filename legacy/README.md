# Legacy Scripts

This directory contains the original, monolithic versions of ArbiBot scripts that have been refactored into the new modular architecture.

## Files

### arbitrage_analysis.py
**Status:** Deprecated - Replaced by `services/historical_validator.py`

Original script for analyzing arbitrage opportunities using historical data. This was a standalone script with hardcoded configuration and no modular structure.

**Replaced by:**
- `services/historical_validator.py` - Modular class-based implementation
- `utils/metrics.py` - Extracted statistical functions
- `config/config.yaml` - Externalized configuration

### market_scanner.py
**Status:** Deprecated - Replaced by `services/market_scanner.py`

Original script for scanning multiple trading pairs across exchanges. This was a standalone script with embedded logic and no integration with other modules.

**Replaced by:**
- `services/market_scanner.py` - Modular class-based implementation
- Integration with `HistoricalValidator` for analysis
- Whitelist generation to `config/whitelist.json`

## Why These Were Refactored

1. **Modularity**: Original scripts were monolithic with mixed concerns
2. **Reusability**: Functions were not easily reusable across different parts of the codebase
3. **Configuration**: Settings were hardcoded rather than externalized
4. **Logging**: Used print statements instead of proper logging framework
5. **Testing**: Difficult to unit test due to tight coupling
6. **Maintainability**: Changes required editing multiple places in large files

## Migration Guide

If you were using the old scripts:

### Old Way (arbitrage_analysis.py)
```bash
python arbitrage_analysis.py
```

### New Way (historical_validator.py)
```bash
python -m services.historical_validator BTC/USDT --timeframe 15m --limit 1000
```

### Old Way (market_scanner.py)
```bash
python market_scanner.py
```

### New Way (market_scanner.py)
```bash
python -m services.market_scanner --config config/config.yaml
```

## Preservation Reason

These files are kept for reference purposes only. They demonstrate the evolution of the codebase and may be useful for:
- Understanding the original implementation approach
- Comparing old vs new architecture
- Historical reference during debugging

**Do not use these scripts in production.** Use the new modular services instead.

---

*Last Updated: 2025-12-02*
*Refactored By: Senior Python Developer*
