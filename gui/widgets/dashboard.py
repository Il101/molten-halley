"""
Dashboard Widget for ArbiBot GUI

Real-time price monitoring with Z-Score visualization.
"""

import sys
from pathlib import Path
from typing import Dict, Optional
from collections import deque
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
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
        
        # Data buffer for table updates
        self.table_data_buffer: Dict[str, Dict] = {}
        self.price_cache: Dict[str, float] = {}  # symbol -> bingx_price (for calculations)
        
        # Setup update timer (throttle UI updates to 10 FPS)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._refresh_ui)
        self.update_timer.start(100)  # 100ms interval
    
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
        
        # Prevent auto-scaling from zooming in too much on noise
        # This fixes the "jitter" when Z-score is small (e.g. 0.22)
        self.chart.getViewBox().setLimits(minYRange=5)  # Always show at least range of 5 (e.g. -2.5 to 2.5)
        
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
        
        # Buffer data for table update
        if symbol not in self.table_data_buffer:
            self.table_data_buffer[symbol] = {}
            
        if exchange == 'bingx':
            price = data.get('last', 0)
            self.table_data_buffer[symbol]['bingx_price'] = price
            self.price_cache[symbol] = price  # Update cache for calculations
        elif exchange == 'bybit':
            price = data.get('last', 0)
            self.table_data_buffer[symbol]['bybit_price'] = price
    
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
        # Use cached BingX price as base
        bingx_price = self.price_cache.get(symbol, 0)
        if bingx_price > 0:
            spread_pct = (abs(spread) / bingx_price) * 100
        else:
            spread_pct = 0
        
        # Update spread %
        # OPTIMIZATION: Buffer for timer update
        # spread_item = self._create_item(f"{spread_pct:.3f}%")
        # self.table.setItem(row, 3, spread_item)
        
        # Update Z-Score with color coding
        # ... (removed direct updates) ...
        
        # Store Z-Score history
        if symbol not in self.z_score_history:
            self.z_score_history[symbol] = deque(maxlen=self.max_history_points)
        
        self.z_score_history[symbol].append((time.time(), z_score))
        
        # Update chart if this symbol is selected
        # OPTIMIZATION: Don't update chart here, let the timer handle it
        # if symbol == self.selected_symbol:
        #     self._update_chart(symbol)
    
        # Store latest data for table update
        if symbol not in self.table_data_buffer:
            self.table_data_buffer[symbol] = {}
        
        self.table_data_buffer[symbol].update({
            'spread_pct': spread_pct,
            'z_score': z_score
        })

    def _refresh_ui(self):
        """Timer slot to refresh UI (Chart + Table)."""
        if not self.isVisible():
            return

        # 1. Update Chart
        if self.selected_symbol:
            self._update_chart(self.selected_symbol)
            
        # 2. Update Table
        for symbol, data in self.table_data_buffer.items():
            if symbol not in self.rows:
                continue
                
            row = self.rows[symbol]
            
            # Update prices
            if 'bingx_price' in data:
                self._update_item_text(row, 1, f"${data['bingx_price']:,.2f}")
            if 'bybit_price' in data:
                self._update_item_text(row, 2, f"${data['bybit_price']:,.2f}")
                
            # Update spread/z-score
            if 'spread_pct' in data:
                self._update_item_text(row, 3, f"{data['spread_pct']:.3f}%")
            
            if 'z_score' in data:
                z_score = data['z_score']
                self._update_item_text(row, 4, f"{z_score:.2f}")
                
                # Update colors
                item = self.table.item(row, 4)
                if item:
                    if z_score > 2:
                        item.setBackground(QColor(139, 0, 0))
                        item.setForeground(QColor(255, 255, 255))
                    elif z_score < -2:
                        item.setBackground(QColor(0, 100, 0))
                        item.setForeground(QColor(255, 255, 255))
                    else:
                        item.setBackground(QColor(30, 30, 30))
                        item.setForeground(QColor(200, 200, 200))
                
                # Update status
                if abs(z_score) > 2:
                    status = "🔔 SIGNAL"
                    color = QColor(255, 215, 0)
                else:
                    status = "⏸️ Waiting"
                    color = QColor(150, 150, 150)
                
                self._update_item_text(row, 5, status)
                item = self.table.item(row, 5)
                if item:
                    item.setForeground(color)
        
        # Clear buffer after update? 
        # No, keep it so we don't flicker if no new data comes, 
        # but actually we only want to update if CHANGED.
        # But for simplicity, we can just clear it to avoid re-setting same text.
        self.table_data_buffer.clear()

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

    def _update_item_text(self, row: int, col: int, text: str):
        """
        Update text of an existing item, or create if missing.
        Avoids creating new objects if possible.
        """
        item = self.table.item(row, col)
        if item:
            if item.text() != text:
                item.setText(text)
        else:
            self.table.setItem(row, col, self._create_item(text))
    
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
