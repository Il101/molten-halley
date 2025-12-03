"""
Exchange Implementations

Provides Paper Trading and Real Trading exchange clients.
"""

from .paper import PaperExchange
from .ccxt_wrapper import RealExchange

__all__ = ['PaperExchange', 'RealExchange']
