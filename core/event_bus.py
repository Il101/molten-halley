"""
Event Bus for Inter-Module Communication

Provides a centralized pub/sub system for ArbiBot components.
Uses PyQt6 signals for GUI compatibility.
"""

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False
    class QObject:
        def __init__(self): pass
    
    class SimpleSignal:
        def __init__(self, *args):
            self._callbacks = []
        def connect(self, callback):
            self._callbacks.append(callback)
        def emit(self, *args):
            for callback in self._callbacks:
                try:
                    callback(*args)
                except Exception as e:
                    print(f"Error in signal callback: {e}")

    def pyqtSignal(*args):
        return SimpleSignal(*args)

from typing import Dict, Any


class EventBus(QObject):
    """
    Singleton Event Bus for application-wide event distribution.
    
    Uses PyQt6 signals when available for thread-safe, GUI-compatible event handling.
    Falls back to a native Python implementation in headless environments.
    """
    
    # Singleton instance
    _instance = None
    
    # Signal definitions
    price_updated = pyqtSignal(dict)
    spread_updated = pyqtSignal(dict)
    signal_triggered = pyqtSignal(str, str, float, str, str)
    trade_opened = pyqtSignal(dict)
    trade_closed = pyqtSignal(dict)
    balance_updated = pyqtSignal(dict)
    connection_status = pyqtSignal(str, bool)
    error_occurred = pyqtSignal(str, str)
    log_message = pyqtSignal(str, str)
    
    def __init__(self):
        """Initialize Event Bus (private - use instance() instead)."""
        if EventBus._instance is not None:
            raise RuntimeError("EventBus is a singleton. Use EventBus.instance() instead.")
        
        if HAS_PYQT:
            super().__init__()
        else:
            # Manually initialize signals for headless mode
            # In PyQt, signals are class attributes that become bound on instance creation.
            # In our SimpleSignal fallback, we need them to be instance attributes
            # if we want multiple EventBus instances (though it's a singleton).
            # To match PyQt behavior where signals are defined once:
            self.price_updated = SimpleSignal(dict)
            self.spread_updated = SimpleSignal(dict)
            self.signal_triggered = SimpleSignal(str, str, float, str, str)
            self.trade_opened = SimpleSignal(dict)
            self.trade_closed = SimpleSignal(dict)
            self.balance_updated = SimpleSignal(dict)
            self.connection_status = SimpleSignal(str, bool)
            self.error_occurred = SimpleSignal(str, str)
            self.log_message = SimpleSignal(str, str)

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
    
    def emit_signal_triggered(self, symbol: str, signal_type: str, z_score: float, ex_a: str = '', ex_b: str = '') -> None:
        """
        Emit a trading signal event.
        
        Args:
            symbol: Trading pair symbol
            signal_type: 'ENTRY' or 'EXIT'
            z_score: Z-Score at signal trigger
            ex_a: First exchange name
            ex_b: Second exchange name
        """
        self.signal_triggered.emit(symbol, signal_type, z_score, ex_a, ex_b)

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
