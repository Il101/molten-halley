"""
Dashboard Widget for ArbiBot GUI

Real-time price monitoring with Z-Score visualization.
"""

import sys
from pathlib import Path
from typing import Dict, Optional
from collections import deque

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QFont
import pyqtgraph as pg

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from core.event_bus import EventBus


class Dashboard(QWidget):
    """
    Main dashboard widget with live price table and Z-Score chart.
    
    Features:
    - Real-time price updates from EventBus
    - Color-coded Z-Score highlighting
    - Interactive Z-Score history chart
    - Efficient O(1) row updates
    """
    
    def __init__(self, parent=None):
        """Initialize dashboard widget."""
        super().__init__(parent)
        
        # Data structures
        self.rows: Dict[str, int] = {}  # symbol -> row_index mapping
        self.z_score_history: Dict[str, deque] = {}  # symbol -> deque of (timestamp, z_score)
        self.max_history_points = 500  # Keep last 500 points
        self.selected_symbol: Optional[str] = None
        
        # Setup UI
        self._setup_ui()
        
        # Connect to EventBus
        self._connect_signals()
    
    def _setup_ui(self):
        """Setup the user interface."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Splitter for table and chart
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # === Price Table ===
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            'Symbol', 'BingX Price', 'Bybit Price', 'Spread %', 'Z-Score', 'Status'
        ])
        
        # Table styling
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        
        # Font
        font = QFont("Consolas", 10)
        self.table.setFont(font)
        
        # Connect selection change
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        
        # === Z-Score Chart ===
        self.chart = pg.PlotWidget()
        self.chart.setBackground('#1e1e1e')
        self.chart.setTitle("Z-Score History", color='w', size='12pt')
        self.chart.setLabel('left', 'Z-Score', color='w')
        self.chart.setLabel('bottom', 'Time', color='w')
        self.chart.showGrid(x=True, y=True, alpha=0.3)
        self.chart.addLegend()
        
        # Add threshold lines
        self.chart.addLine(y=2, pen=pg.mkPen('r', width=2, style=Qt.PenStyle.DashLine), label='Entry (+2)')
        self.chart.addLine(y=-2, pen=pg.mkPen('g', width=2, style=Qt.PenStyle.DashLine), label='Entry (-2)')
        self.chart.addLine(y=0, pen=pg.mkPen('w', width=1, style=Qt.PenStyle.DotLine), label='Mean')
        
        # Chart data line
        self.chart_line = self.chart.plot([], [], pen=pg.mkPen('c', width=2), name='Z-Score')
        
        # Add widgets to splitter
        splitter.addWidget(self.table)
        splitter.addWidget(self.chart)
        splitter.setSizes([400, 300])  # Initial sizes
        
        layout.addWidget(splitter)
    
    def _connect_signals(self):
        """Connect to EventBus signals."""
        bus = EventBus.instance()
        bus.price_updated.connect(self._on_price_update)
        bus.spread_updated.connect(self._on_spread_update)
        bus.connection_status.connect(self._on_connection_status)
    
    @pyqtSlot(dict)
    def _on_price_update(self, data: dict):
        """
        Handle price update from EventBus.
        
        Args:
            data: Price data dict with keys: exchange, symbol, bid, ask, last
        """
        symbol = data.get('symbol')
        if not symbol:
            return
        
        # Ensure row exists
        if symbol not in self.rows:
            self._add_row(symbol)
        
        row = self.rows[symbol]
        exchange = data.get('exchange')
        
        # Update price column
        if exchange == 'bingx':
            price = data.get('last', 0)
            self.table.setItem(row, 1, self._create_item(f"${price:,.2f}"))
        elif exchange == 'bybit':
            price = data.get('last', 0)
            self.table.setItem(row, 2, self._create_item(f"${price:,.2f}"))
    
    @pyqtSlot(str, float, float)
    def _on_spread_update(self, symbol: str, spread: float, z_score: float):
        """
        Handle spread/Z-Score update from EventBus.
        
        Args:
            symbol: Trading pair symbol
            spread: Current spread value
            z_score: Current Z-Score
        """
        # Ensure row exists
        if symbol not in self.rows:
            self._add_row(symbol)
        
        row = self.rows[symbol]
        
        # Calculate spread percentage (approximate)
        # We'll use the BingX price as base if available
        bingx_item = self.table.item(row, 1)
        if bingx_item:
            try:
                bingx_price = float(bingx_item.text().replace('$', '').replace(',', ''))
                spread_pct = (abs(spread) / bingx_price) * 100 if bingx_price > 0 else 0
            except:
                spread_pct = 0
        else:
            spread_pct = 0
        
        # Update spread %
        spread_item = self._create_item(f"{spread_pct:.3f}%")
        self.table.setItem(row, 3, spread_item)
        
        # Update Z-Score with color coding
        z_score_item = self._create_item(f"{z_score:.2f}")
        if z_score > 2:
            z_score_item.setBackground(QColor(139, 0, 0))  # Dark red
            z_score_item.setForeground(QColor(255, 255, 255))
        elif z_score < -2:
            z_score_item.setBackground(QColor(0, 100, 0))  # Dark green
            z_score_item.setForeground(QColor(255, 255, 255))
        else:
            z_score_item.setBackground(QColor(30, 30, 30))
            z_score_item.setForeground(QColor(200, 200, 200))
        
        self.table.setItem(row, 4, z_score_item)
        
        # Update status
        if abs(z_score) > 2:
            status = "🔔 SIGNAL"
            status_item = self._create_item(status)
            status_item.setForeground(QColor(255, 215, 0))  # Gold
        else:
            status = "⏸️ Waiting"
            status_item = self._create_item(status)
            status_item.setForeground(QColor(150, 150, 150))
        
        self.table.setItem(row, 5, status_item)
        
        # Store Z-Score history
        if symbol not in self.z_score_history:
            self.z_score_history[symbol] = deque(maxlen=self.max_history_points)
        
        import time
        self.z_score_history[symbol].append((time.time(), z_score))
        
        # Update chart if this symbol is selected
        if symbol == self.selected_symbol:
            self._update_chart(symbol)
    
    @pyqtSlot(str, bool)
    def _on_connection_status(self, exchange: str, connected: bool):
        """
        Handle connection status change.
        
        Args:
            exchange: Exchange name
            connected: Connection status
        """
        # Could update a status bar or indicator here
        pass
    
    def _add_row(self, symbol: str):
        """
        Add a new row for a symbol.
        
        Args:
            symbol: Trading pair symbol
        """
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.rows[symbol] = row
        
        # Set symbol
        symbol_item = self._create_item(symbol)
        symbol_item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.table.setItem(row, 0, symbol_item)
        
        # Set loading placeholders
        for col in range(1, 6):
            self.table.setItem(row, col, self._create_item("Loading..."))
    
    def _create_item(self, text: str) -> QTableWidgetItem:
        """
        Create a table item with consistent styling.
        
        Args:
            text: Item text
            
        Returns:
            Configured QTableWidgetItem
        """
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        return item
    
    def _on_selection_changed(self):
        """Handle table row selection change."""
        selected = self.table.selectedItems()
        if selected:
            row = selected[0].row()
            symbol_item = self.table.item(row, 0)
            if symbol_item:
                self.selected_symbol = symbol_item.text()
                self._update_chart(self.selected_symbol)
    
    def _update_chart(self, symbol: str):
        """
        Update Z-Score chart for selected symbol.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol not in self.z_score_history:
            self.chart_line.setData([], [])
            return
        
        history = list(self.z_score_history[symbol])
        if not history:
            self.chart_line.setData([], [])
            return
        
        # Extract timestamps and z_scores
        timestamps, z_scores = zip(*history)
        
        # Convert to relative time (seconds from first point)
        if timestamps:
            base_time = timestamps[0]
            relative_times = [t - base_time for t in timestamps]
            
            # Update chart
            self.chart_line.setData(relative_times, z_scores)
            self.chart.setTitle(f"Z-Score History - {symbol}", color='w', size='12pt')
