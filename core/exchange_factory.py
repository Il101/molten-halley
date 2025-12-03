"""
Exchange Factory

Creates exchange clients based on configuration and mode.
"""

from typing import Dict, Optional, Any
from core.interfaces.exchange import BaseExchange
from core.exchanges.paper import PaperExchange
from core.exchanges.ccxt_wrapper import RealExchange
from utils.logger import get_logger

logger = get_logger(__name__)

def create_exchange_client(
    name: str,
    config: Dict[str, Any],
    mode: str = 'PAPER',
    ws_manager: Optional[Any] = None
) -> BaseExchange:
    """
    Factory function to create exchange clients.
    
    Args:
        name: Exchange name ('bingx' or 'bybit')
        config: Configuration dictionary
        mode: Trading mode ('PAPER' or 'LIVE')
        ws_manager: WebSocketManager instance (required for PAPER mode)
    
    Returns:
        BaseExchange implementation
    """
    if mode == 'PAPER':
        if ws_manager is None:
            raise ValueError("WebSocketManager is required for PAPER trading mode")
        
        paper_balance = config.get('trading', {}).get('paper_balance', 10000.0)
        fee_rate = config.get('trading', {}).get('fee_rate', 0.0006)
        
        return PaperExchange(
            exchange_name=name,
            initial_balance=paper_balance,
            ws_manager=ws_manager,
            fee_rate=fee_rate
        )
        
    elif mode == 'LIVE':
        exchange_config = config.get('exchanges', {}).get(name, {})
        api_key = exchange_config.get('api_key')
        api_secret = exchange_config.get('api_secret')
        testnet = exchange_config.get('testnet', False)
        
        if not api_key or not api_secret:
            raise ValueError(f"API credentials missing for {name} in LIVE mode")
            
        return RealExchange(
            exchange_name=name,
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet
        )
        
    else:
        raise ValueError(f"Invalid trading mode: {mode}")
