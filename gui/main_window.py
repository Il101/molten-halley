"""
Main Window for ArbiBot GUI

Professional desktop application with real-time arbitrage monitoring.
Integrates all widgets with qasync for async/Qt event loop fusion.
"""

import sys
import asyncio
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStatusBar,
    QMenuBar, QMenu, QMessageBox, QSplitter, QDockWidget
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QPalette, QColor

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from gui.widgets.pair_selector import PairSelector
from gui.widgets.monitor_table import MonitorTable
from gui.widgets.zscore_chart import ZScoreChart
from gui.widgets.connection_status import ConnectionStatus
from services.live_monitor import LiveMonitor
from core.event_bus import EventBus
from core.event_bus import EventBus
from utils.logger import get_logger
from core.exchange_factory import create_exchange_client
from services.execution import ExecutionEngine
from gui.widgets.active_trades import ActiveTradesWidget


class MainWindow(QMainWindow):
    """
    Main application window for ArbiBot.
    
    Features:
    - Real-time price monitoring with color-coded Z-Scores
    - Dynamic pair management (add/remove at runtime)
    - Z-Score visualization chart
    - Connection status monitoring
    - Dark theme UI
    - Async WebSocket integration via qasync
    - Graceful shutdown handling
    """
    
    def __init__(self):
        """Initialize main window."""
        super().__init__()
        
        self.logger = get_logger(__name__)
        self.live_monitor: Optional[LiveMonitor] = None
        self.monitor_task: Optional[asyncio.Task] = None
        self.execution_engine: Optional[ExecutionEngine] = None
        
        # Setup UI
        self._setup_ui()
        self._apply_dark_theme()
        self._create_dock_widgets()
        self._create_menu_bar()
        
        # Connect signals
        self._connect_signals()
        
        # Start monitoring with initial symbols
        QTimer.singleShot(100, self._start_monitoring)
    
    def _setup_ui(self):
        """Setup the user interface."""
        self.setWindowTitle("ArbiBot - Professional Crypto Arbitrage Monitor")
        self.setGeometry(100, 100, 1400, 900)
        
        # Central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Main splitter (horizontal: table | chart)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Monitor table (left side)
        self.monitor_table = MonitorTable()
        self.main_splitter.addWidget(self.monitor_table)
        
        # Z-Score chart (right side)
        self.zscore_chart = ZScoreChart()
        self.main_splitter.addWidget(self.zscore_chart)
        
        # Set initial splitter sizes (60% table, 40% chart)
        self.main_splitter.setSizes([840, 560])
        
        layout.addWidget(self.main_splitter)
        
        # Active Trades Widget (Bottom)
        self.active_trades_widget = ActiveTradesWidget()
        self.active_trades_widget.setMaximumHeight(200)
        layout.addWidget(self.active_trades_widget)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Initializing...")
    
    def _create_dock_widgets(self):
        """Create dock widgets for pair selector and connection status."""
        # Pair selector dock (left)
        self.pair_selector_dock = QDockWidget("Pair Management", self)
        self.pair_selector_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.pair_selector = PairSelector()
        self.pair_selector_dock.setWidget(self.pair_selector)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.pair_selector_dock)
        
        # Connection status dock (bottom)
        self.connection_dock = QDockWidget("Connection Status", self)
        self.connection_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.connection_status = ConnectionStatus()
        self.connection_dock.setWidget(self.connection_status)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.connection_dock)
    
    def _create_menu_bar(self):
        """Create application menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        refresh_whitelist_action = QAction("&Refresh Whitelist", self)
        refresh_whitelist_action.setShortcut("Ctrl+R")
        refresh_whitelist_action.triggered.connect(self._refresh_whitelist)
        tools_menu.addAction(refresh_whitelist_action)
        
        tools_menu.addSeparator()
        
        clear_chart_action = QAction("&Clear Chart", self)
        clear_chart_action.triggered.connect(self._clear_chart)
        tools_menu.addAction(clear_chart_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        view_menu.addAction(self.pair_selector_dock.toggleViewAction())
        view_menu.addAction(self.connection_dock.toggleViewAction())
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _apply_dark_theme(self):
        """Apply professional dark theme to the application."""
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
        
        # Additional stylesheet for widgets
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QDockWidget {
                color: #c8c8c8;
                font-weight: bold;
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 5px;
            }
            QMenuBar {
                background-color: #2d2d2d;
                color: #c8c8c8;
            }
            QMenuBar::item:selected {
                background-color: #3d3d3d;
            }
            QMenu {
                background-color: #2d2d2d;
                color: #c8c8c8;
            }
            QMenu::item:selected {
                background-color: #3d3d3d;
            }
        """)
    
    def _connect_signals(self):
        """Connect widget signals."""
        # Pair selector signals
        self.pair_selector.pair_added.connect(self._on_pair_added)
        self.pair_selector.pair_removed.connect(self._on_pair_removed)
        
        # Table selection for chart
        self.monitor_table.table.itemSelectionChanged.connect(self._on_table_selection_changed)
    
    def _start_monitoring(self):
        """Start the live monitoring service."""
        try:
            # Create LiveMonitor
            self.live_monitor = LiveMonitor(config_path='config/config.yaml')
            
            # Get initial symbols from whitelist (or default)
            initial_symbols = self.pair_selector.get_active_pairs()
            if not initial_symbols:
                initial_symbols = ['BTC/USDT']  # Default
                self.pair_selector.add_active_pair('BTC/USDT')
                self.monitor_table.add_symbol('BTC/USDT')
                self.zscore_chart.set_symbol('BTC/USDT')
            
            # Start monitoring in async task
            self.monitor_task = asyncio.create_task(
                self.live_monitor.start(initial_symbols)
            )
            
            self.status_bar.showMessage(f"Monitoring {len(initial_symbols)} pair(s)...")
            self.logger.info(f"Started monitoring: {initial_symbols}")
            
            # Initialize Execution Engine
            self._init_execution_engine()
            
        except Exception as e:
            self.logger.error(f"Error starting monitor: {e}", exc_info=True)
            self.status_bar.showMessage(f"Error: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to start monitoring:\n{e}"
            )
    
    def _on_pair_added(self, symbol: str):
        """
        Handle pair added signal.
        
        Args:
            symbol: Trading pair symbol
        """
        try:
            if self.live_monitor:
                # Subscribe to new symbol
                asyncio.create_task(
                    self.live_monitor.ws_manager.subscribe([symbol])
                )
                
                # Add to table
                self.monitor_table.add_symbol(symbol)
                
                # Always switch chart to newly added symbol
                self.zscore_chart.set_symbol(symbol)
                
                self.status_bar.showMessage(f"Added {symbol} to monitoring")
                self.logger.info(f"Subscribed to {symbol}")
            
        except Exception as e:
            self.logger.error(f"Error adding pair {symbol}: {e}")
            QMessageBox.warning(self, "Error", f"Failed to add {symbol}:\n{e}")
    
    def _on_pair_removed(self, symbol: str):
        """
        Handle pair removed signal.
        
        Args:
            symbol: Trading pair symbol
        """
        try:
            if self.live_monitor:
                # Unsubscribe from symbol
                asyncio.create_task(
                    self.live_monitor.ws_manager.unsubscribe([symbol])
                )
                
                # Remove from table
                self.monitor_table.remove_symbol(symbol)
                
                # Clear chart if this was the selected symbol
                if self.zscore_chart.selected_symbol == symbol:
                    self.zscore_chart.clear_data()
                
                self.status_bar.showMessage(f"Removed {symbol} from monitoring")
                self.logger.info(f"Unsubscribed from {symbol}")
            
        except Exception as e:
            self.logger.error(f"Error removing pair {symbol}: {e}")
            QMessageBox.warning(self, "Error", f"Failed to remove {symbol}:\n{e}")
    
    def _on_table_selection_changed(self):
        """Handle table row selection change."""
        selected_items = self.monitor_table.table.selectedItems()
        
        if selected_items:
            # Get symbol from first column of selected row
            row = selected_items[0].row()
            symbol_item = self.monitor_table.table.item(row, MonitorTable.COL_SYMBOL)
            
            if symbol_item:
                symbol = symbol_item.text()
                self.zscore_chart.set_symbol(symbol)
                self.status_bar.showMessage(f"Chart now showing: {symbol}")
    
    def _refresh_whitelist(self):
        """Refresh whitelist from file."""
        try:
            self.pair_selector.refresh_whitelist()
            self.status_bar.showMessage("Whitelist refreshed")
            QMessageBox.information(
                self,
                "Success",
                "Whitelist reloaded successfully"
            )
        except Exception as e:
            self.logger.error(f"Error refreshing whitelist: {e}")
            QMessageBox.warning(self, "Error", f"Failed to refresh whitelist:\n{e}")
    
    def _clear_chart(self):
        """Clear chart data."""
        self.zscore_chart.clear_data()
        self.status_bar.showMessage("Chart cleared")
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About ArbiBot",
            "<h2>ArbiBot</h2>"
            "<p><b>Professional Cryptocurrency Arbitrage Monitor</b></p>"
            "<p>Real-time monitoring of arbitrage opportunities "
            "between BingX and Bybit exchanges.</p>"
            "<hr>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Dynamic pair management</li>"
            "<li>Real-time Z-Score calculation</li>"
            "<li>Color-coded signal indicators</li>"
            "<li>High-performance charting</li>"
            "</ul>"
            "<hr>"
            "<p><b>Version:</b> 2.0.0</p>"
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
            self.logger.info("Shutting down...")
            
            if self.live_monitor:
                await self.live_monitor.stop()
            
            if self.monitor_task and not self.monitor_task.done():
                self.monitor_task.cancel()
                try:
                    await self.monitor_task
                except asyncio.CancelledError:
                    pass
            
            self.logger.info("Shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)
    def _init_execution_engine(self):
        """Initialize Execution Engine with Paper/Real clients."""
        try:
            config = self.live_monitor.config
            mode = config.get('trading', {}).get('mode', 'PAPER')
            
            # Create clients
            client_a = create_exchange_client(
                'bingx', config, mode, self.live_monitor.ws_manager
            )
            client_b = create_exchange_client(
                'bybit', config, mode, self.live_monitor.ws_manager
            )
            
            # Create Engine
            self.execution_engine = ExecutionEngine(
                client_a, client_b,
                position_size_usdt=config.get('trading', {}).get('position_size_usdt', 100.0)
            )
            
            self.logger.info(f"Execution Engine initialized in {mode} mode")
            self.status_bar.showMessage(f"Monitoring {len(self.pair_selector.get_active_pairs())} pairs | Trading: {mode}")
            
        except Exception as e:
            self.logger.error(f"Failed to init Execution Engine: {e}")
            QMessageBox.critical(self, "Error", f"Failed to init Execution Engine:\n{e}")
