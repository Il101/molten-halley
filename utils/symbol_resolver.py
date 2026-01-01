"""
Symbol Resolver Utility

Provides robust resolution of generic trading pairs (e.g., 'BTC/USDT') to 
exchange-specific market symbols (e.g., 'BTC/USDT:USDT' or 'BDXN/USDT').
"""

from typing import Dict, List, Optional
import ccxt
from utils.logger import get_logger

class SymbolResolver:
    """
    Resolves and caches exchange-specific symbols.
    """
    
    def __init__(self, config: Optional[dict] = None):
        self.logger = get_logger(__name__)
        self.config = config or {}
        self.cache: Dict[str, Dict[str, str]] = {} # exchange -> {query -> actual}
        
    async def resolve(self, exchange: ccxt.Exchange, query_symbol: str) -> Optional[str]:
        """
        Find the best match for a symbol on a specific exchange.
        """
        ex_id = exchange.id
        if ex_id not in self.cache:
            self.cache[ex_id] = {}
            
        if query_symbol in self.cache[ex_id]:
            return self.cache[ex_id][query_symbol]
            
        # Ensure markets are loaded
        if exchange.symbols is None:
            self.logger.info(f"🔄 Loading markets for {ex_id}...")
            await exchange.load_markets()
            
        if exchange.symbols is None:
            self.logger.error(f"❌ Failed to load markets for {ex_id}")
            return None
            
        # 1. Exact match check
        if query_symbol in exchange.symbols:
            self.cache[ex_id][query_symbol] = query_symbol
            return query_symbol
            
        # 2. Normalize components
        if '/' in query_symbol:
            base, quote = query_symbol.split('/')
        else:
            # Try to guess - very basic
            base, quote = query_symbol[:3], query_symbol[3:] 
            
        # 3. Look for mapping in config (manual overrides)
        manual_map = self.config.get('telegram', {}).get('symbol_mapping', {})
        if base in manual_map:
            mapped_base = manual_map[base]
            mapped_query = f"{mapped_base}/{quote}"
            if mapped_query in exchange.symbols:
                self.cache[ex_id][query_symbol] = mapped_query
                return mapped_query
        
        # 4. Discovery: Search through all symbols
        # Case 1: Partial match (e.g. BDX -> BDXN or BDX/USDT -> BDX/USDT:USDT)
        for sym in exchange.symbols:
            # Check if it's the futures version of the same pair
            if sym.startswith(f"{query_symbol}:"):
                self.cache[ex_id][query_symbol] = sym
                return sym
            
            # Check for renamed base (e.g. BDXN instead of BDX)
            if '/' in sym:
                s_base, s_quote = sym.split('/')
                s_base_clean = s_base.split(':')[0] # Remove :USDT if present
                
                if s_base_clean == base:
                    if s_quote.split(':')[0] == quote:
                        self.logger.info(f"💡 SymbolResolver: Resolved {query_symbol} to {sym} on {ex_id}")
                        self.cache[ex_id][query_symbol] = sym
                        return sym
                        
        return None
