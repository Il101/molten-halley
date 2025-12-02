"""
Main Window for ArbiBot GUI

Desktop application with real-time arbitrage monitoring.
"""

import sys
import asyncio
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStatusBar,
    QMenuBar, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QPalette, QColor

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from gui.widgets.dashboard import Dashboard
from services.live_monitor import LiveMonitor
from core.event_bus import EventBus


class MainWindow(QMainWindow):
    """
    Main application window for ArbiBot.
    
    Features:
    - Real-time price monitoring dashboard
    - Dark theme UI
    - Async WebSocket integration via qasync
    - Graceful shutdown handling
    """
    
    def __init__(self, symbols: list = None):
        """
        Initialize main window.
        
        Args:
            symbols: List of symbols to monitor (default: ['BTC/USDT'])
        """
        super().__init__()
        
        self.symbols = symbols or ['BTC/USDT']
        self.live_monitor: Optional[LiveMonitor] = None
        self.monitor_task: Optional[asyncio.Task] = None
        
        # Setup UI
        self._setup_ui()
        self._apply_dark_theme()
        
        # Start monitoring
        QTimer.singleShot(100, self._start_monitoring)
    
    def _setup_ui(self):
        """Setup the user interface."""
        self.setWindowTitle("ArbiBot - Crypto Arbitrage Monitor")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Dashboard
        self.dashboard = Dashboard()
        layout.addWidget(self.dashboard)
        
        # Menu bar
        self._create_menu_bar()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Initializing...")
    
    def _create_menu_bar(self):
        """Create application menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        refresh_action = QAction("&Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._refresh_data)
        view_menu.addAction(refresh_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _apply_dark_theme(self):
        """Apply dark theme to the application."""
        palette = QPalette()
        
        # Dark colors
        palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(200, 200, 200))
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(200, 200, 200))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(200, 200, 200))
        palette.setColor(QPalette.ColorRole.Text, QColor(200, 200, 200))
        palette.setColor(QPalette.ColorRole.Button, QColor(40, 40, 40))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(200, 200, 200))
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        
        self.setPalette(palette)
    
    def _start_monitoring(self):
        """Start the live monitoring service."""
        try:
            # Create LiveMonitor
            self.live_monitor = LiveMonitor(config_path='config/config.yaml')
            
            # Start monitoring in async task
            self.monitor_task = asyncio.create_task(
                self.live_monitor.start(self.symbols)
            )
            
            self.status_bar.showMessage(f"Monitoring {', '.join(self.symbols)}...")
            
            # Connect to connection status updates
            bus = EventBus.instance()
            bus.connection_status.connect(self._on_connection_status)
            
        except Exception as e:
            self.status_bar.showMessage(f"Error starting monitor: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to start monitoring:\n{e}"
            )
    
    def _on_connection_status(self, exchange: str, connected: bool):
        """
        Handle connection status updates.
        
        Args:
            exchange: Exchange name
            connected: Connection status
        """
        status = "Connected" if connected else "Disconnected"
        self.status_bar.showMessage(f"{exchange.upper()}: {status}")
    
    def _refresh_data(self):
        """Refresh data (placeholder for future implementation)."""
        self.status_bar.showMessage("Refreshing data...")
        QTimer.singleShot(1000, lambda: self.status_bar.showMessage("Ready"))
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About ArbiBot",
            "<h2>ArbiBot</h2>"
            "<p>Cryptocurrency Arbitrage Monitor</p>"
            "<p>Real-time monitoring of arbitrage opportunities "
            "between BingX and Bybit exchanges.</p>"
            "<p><b>Version:</b> 1.0.0</p>"
            "<p><b>Author:</b> ArbiBot Team</p>"
        )
    
    def closeEvent(self, event):
        """
        Handle window close event.
        
        Ensures graceful shutdown of WebSocket connections.
        
        Args:
            event: Close event
        """
        # Ask for confirmation
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Are you sure you want to exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Stop monitoring
            if self.live_monitor:
                asyncio.create_task(self._shutdown())
            
            event.accept()
        else:
            event.ignore()
    
    async def _shutdown(self):
        """Shutdown monitoring service gracefully."""
        try:
            self.status_bar.showMessage("Shutting down...")
            
            if self.live_monitor:
                await self.live_monitor.stop()
            
            if self.monitor_task and not self.monitor_task.done():
                self.monitor_task.cancel()
                try:
                    await self.monitor_task
                except asyncio.CancelledError:
                    pass
            
        except Exception as e:
            print(f"Error during shutdown: {e}")
