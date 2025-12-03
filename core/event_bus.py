"""
Event Bus for Inter-Module Communication

Provides a centralized pub/sub system for ArbiBot components.
Uses PyQt6 signals for GUI compatibility.
"""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, Any


class EventBus(QObject):
    """
    Singleton Event Bus for application-wide event distribution.
    
    Uses PyQt6 signals for thread-safe, GUI-compatible event handling.
    All components can emit and subscribe to events through this bus.
    """
    
    # Singleton instance
    _instance = None
    
    # Signal definitions
    price_updated = pyqtSignal(dict)  # Emitted on each price update
    spread_updated = pyqtSignal(dict)  # Emitted with comprehensive spread data (gross, fee, net, z_score)
    signal_triggered = pyqtSignal(str, str, float)  # (symbol, 'ENTRY'|'EXIT', z_score)
    trade_opened = pyqtSignal(dict)  # Payload: {symbol, size, entry_price, side, ...}
    trade_closed = pyqtSignal(dict)  # Payload: {symbol, pnl, exit_price, ...}
    balance_updated = pyqtSignal(dict) # Payload: {exchange, available, total}
    connection_status = pyqtSignal(str, bool)  # (exchange, connected)
    error_occurred = pyqtSignal(str, str)  # (component, error_message)
    log_message = pyqtSignal(str, str) # level, message (for GUI log console)
    
    def __init__(self):
        """Initialize Event Bus (private - use instance() instead)."""
        if EventBus._instance is not None:
            raise RuntimeError("EventBus is a singleton. Use EventBus.instance() instead.")
        
        super().__init__()
        EventBus._instance = self
    
    @classmethod
    def instance(cls) -> 'EventBus':
        """
        Get the singleton instance of EventBus.
        
        Returns:
            EventBus singleton instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (for testing purposes)."""
        cls._instance = None
    
    # Convenience methods for emitting events
    
    def emit_price_update(self, data: Dict[str, Any]) -> None:
        """
        Emit a price update event.
        
        Args:
            data: Normalized price data dictionary
        """
        self.price_updated.emit(data)
    
    def emit_signal_triggered(self, symbol: str, signal_type: str, z_score: float) -> None:
        """
        Emit a trading signal event.
        
        Args:
            symbol: Trading pair symbol
            signal_type: 'ENTRY' or 'EXIT'
            z_score: Z-Score at signal trigger
        """
        self.signal_triggered.emit(symbol, signal_type, z_score)

    def emit_trade_opened(self, trade_data: Dict[str, Any]) -> None:
        """Emit trade opened event."""
        self.trade_opened.emit(trade_data)

    def emit_trade_closed(self, trade_data: Dict[str, Any]) -> None:
        """Emit trade closed event."""
        self.trade_closed.emit(trade_data)

    def emit_balance_update(self, balance_data: Dict[str, Any]) -> None:
        """Emit balance update event."""
        self.balance_updated.emit(balance_data)

    def emit_log(self, level: str, message: str) -> None:
        """Emit log message event."""
        self.log_message.emit(level, message)
    
    def emit_connection_status(self, exchange: str, connected: bool) -> None:
        """
        Emit connection status change event.
        
        Args:
            exchange: Exchange name
            connected: Connection status
        """
        self.connection_status.emit(exchange, connected)
    
    def emit_error(self, component: str, error_message: str) -> None:
        """
        Emit an error event.
        
        Args:
            component: Component name where error occurred
            error_message: Error description
        """
        self.error_occurred.emit(component, error_message)
