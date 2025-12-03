"""
Connection Status Widget

Displays real-time connection status for BingX and Bybit exchanges.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont

from core.event_bus import EventBus
from utils.logger import get_logger


class ConnectionStatus(QWidget):
    """
    Connection status indicator widget.
    
    Features:
    - Real-time connection status for BingX and Bybit
    - Color-coded indicators (🟢 Connected / 🔴 Disconnected)
    - Auto-refresh heartbeat every 5 seconds
    - EventBus integration
    """
    
    def __init__(self):
        """Initialize connection status widget."""
        super().__init__()
        
        self.logger = get_logger(__name__)
        self.connection_states = {
            'bingx': False,
            'bybit': False
        }
        
        self._setup_ui()
        self._connect_signals()
        self._start_heartbeat()
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Title
        title = QLabel("Connection Status:")
        title_font = QFont()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Separator
        separator1 = self._create_separator()
        layout.addWidget(separator1)
        
        # BingX status
        self.bingx_label = QLabel("BingX: 🔴 Disconnected")
        self.bingx_label.setStyleSheet("color: #e74c3c;")
        layout.addWidget(self.bingx_label)
        
        # Separator
        separator2 = self._create_separator()
        layout.addWidget(separator2)
        
        # Bybit status
        self.bybit_label = QLabel("Bybit: 🔴 Disconnected")
        self.bybit_label.setStyleSheet("color: #e74c3c;")
        layout.addWidget(self.bybit_label)
        
        # Stretch to push everything to the left
        layout.addStretch()
    
    def _create_separator(self) -> QFrame:
        """
        Create a vertical separator line.
        
        Returns:
            QFrame configured as separator
        """
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        return separator
    
    def _connect_signals(self):
        """Connect to EventBus signals."""
        bus = EventBus.instance()
        bus.connection_status.connect(self._on_connection_status)
    
    def _start_heartbeat(self):
        """Start heartbeat timer for auto-refresh."""
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self._heartbeat_check)
        self.heartbeat_timer.start(5000)  # 5 seconds
        self.logger.debug("Heartbeat timer started (5s interval)")
    
    @pyqtSlot(str, bool)
    def _on_connection_status(self, exchange: str, connected: bool):
        """
        Handle connection status update from EventBus.
        
        Args:
            exchange: Exchange name ('bingx' or 'bybit')
            connected: Connection status
        """
        exchange_lower = exchange.lower()
        
        if exchange_lower not in self.connection_states:
            self.logger.warning(f"Unknown exchange: {exchange}")
            return
        
        self.connection_states[exchange_lower] = connected
        self._update_display(exchange_lower, connected)
        
        self.logger.debug(f"{exchange} connection status: {connected}")
    
    def _update_display(self, exchange: str, connected: bool):
        """
        Update the display for an exchange.
        
        Args:
            exchange: Exchange name
            connected: Connection status
        """
        if connected:
            status_text = f"{exchange.upper()}: 🟢 Connected"
            color = "#2ecc71"  # Green
        else:
            status_text = f"{exchange.upper()}: 🔴 Disconnected"
            color = "#e74c3c"  # Red
        
        if exchange == 'bingx':
            self.bingx_label.setText(status_text)
            self.bingx_label.setStyleSheet(f"color: {color};")
        elif exchange == 'bybit':
            self.bybit_label.setText(status_text)
            self.bybit_label.setStyleSheet(f"color: {color};")
    
    def _heartbeat_check(self):
        """
        Periodic heartbeat check.
        
        Refreshes display based on current connection states.
        """
        for exchange, connected in self.connection_states.items():
            self._update_display(exchange, connected)
    
    def get_connection_states(self) -> dict:
        """
        Get current connection states.
        
        Returns:
            Dictionary of exchange: connected status
        """
        return self.connection_states.copy()
