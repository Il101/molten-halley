"""
Z-Score Chart Widget

Real-time line chart for Z-Score visualization using pyqtgraph.
"""

from collections import deque
from typing import Optional
import time

import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtGui import QColor

from core.event_bus import EventBus
from utils.logger import get_logger


class ZScoreChart(QWidget):
    """
    Real-time Z-Score chart using pyqtgraph for performance.
    
    Features:
    - Rolling buffer (200 points max)
    - Reference lines at ±2.5, ±2, 0
    - Color-filled zones (red above +2, green below -2)
    - Updates only for selected symbol
    """
    
    def __init__(self, max_points: int = 200):
        """
        Initialize Z-Score chart.
        
        Args:
            max_points: Maximum number of points to display
        """
        super().__init__()
        
        self.logger = get_logger(__name__)
        self.max_points = max_points
        self.selected_symbol: Optional[str] = None
        
        # Data buffers
        self.timestamps = deque(maxlen=max_points)
        self.zscores = deque(maxlen=max_points)
        self.data_counter = 0  # Continuous counter for X-axis
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Title
        self.title_label = QLabel("Z-Score Chart - No Symbol Selected")
        self.title_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        layout.addWidget(self.title_label)
        
        # Create plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.setLabel('left', 'Z-Score')
        self.plot_widget.setLabel('bottom', 'Time (samples)')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        # Add reference lines
        self._add_reference_lines()
        
        # Main data curve
        self.curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#3498db', width=2),
            name='Z-Score'
        )
        
        # Fill regions
        self._add_fill_regions()
        
        layout.addWidget(self.plot_widget)
    
    def _add_reference_lines(self):
        """Add horizontal reference lines."""
        # Zero line (white)
        self.plot_widget.addLine(y=0, pen=pg.mkPen(color='w', width=1, style=pg.QtCore.Qt.PenStyle.DashLine))
        
        # +2 and -2 lines (yellow)
        self.plot_widget.addLine(y=2.0, pen=pg.mkPen(color='#f39c12', width=1, style=pg.QtCore.Qt.PenStyle.DashLine))
        self.plot_widget.addLine(y=-2.0, pen=pg.mkPen(color='#f39c12', width=1, style=pg.QtCore.Qt.PenStyle.DashLine))
        
        # +2.5 and -2.5 lines (red/green)
        self.plot_widget.addLine(y=2.5, pen=pg.mkPen(color='#e74c3c', width=1, style=pg.QtCore.Qt.PenStyle.DotLine))
        self.plot_widget.addLine(y=-2.5, pen=pg.mkPen(color='#2ecc71', width=1, style=pg.QtCore.Qt.PenStyle.DotLine))
    
    def _add_fill_regions(self):
        """Add colored fill regions for signal zones."""
        # Red zone (above +2)
        self.red_fill = pg.LinearRegionItem(
            values=[2.0, 5.0],
            orientation='horizontal',
            brush=pg.mkBrush(220, 53, 69, 50),
            movable=False
        )
        self.plot_widget.addItem(self.red_fill)
        
        # Green zone (below -2)
        self.green_fill = pg.LinearRegionItem(
            values=[-5.0, -2.0],
            orientation='horizontal',
            brush=pg.mkBrush(40, 167, 69, 50),
            movable=False
        )
        self.plot_widget.addItem(self.green_fill)
    
    def _connect_signals(self):
        """Connect to EventBus signals."""
        bus = EventBus.instance()
        bus.spread_updated.connect(self._on_spread_updated)
    
    @pyqtSlot(str, float, float)
    def _on_spread_updated(self, symbol: str, spread: float, zscore: float):
        """
        Handle spread update from EventBus.
        
        Only updates if symbol matches selected symbol.
        
        Args:
            symbol: Trading pair symbol
            spread: Spread value
            zscore: Z-Score value
        """
        # Only update for selected symbol
        if self.selected_symbol is None or symbol != self.selected_symbol:
            return
        
        try:
            # Add to buffers with continuous counter
            self.timestamps.append(self.data_counter)
            self.zscores.append(zscore)
            self.data_counter += 1
            
            # Update plot
            self.curve.setData(list(self.timestamps), list(self.zscores))
            
            # Auto-scroll: adjust X-axis to show last max_points
            if len(self.timestamps) >= self.max_points:
                # Show the most recent data window
                x_min = self.timestamps[0]
                x_max = self.timestamps[-1]
                self.plot_widget.setXRange(x_min, x_max, padding=0)
            
        except Exception as e:
            self.logger.error(f"Error updating chart: {e}")
    
    def set_symbol(self, symbol: str):
        """
        Set the symbol to monitor.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol == self.selected_symbol:
            return
        
        self.selected_symbol = symbol
        self.title_label.setText(f"Z-Score Chart - {symbol}")
        
        # Clear buffers
        self.timestamps.clear()
        self.zscores.clear()
        self.data_counter = 0
        self.curve.setData([], [])
        
        self.logger.info(f"Chart now monitoring: {symbol}")
    
    def clear_data(self):
        """Clear all chart data."""
        self.timestamps.clear()
        self.zscores.clear()
        self.data_counter = 0
        self.curve.setData([], [])
        self.selected_symbol = None
        self.title_label.setText("Z-Score Chart - No Symbol Selected")
        self.logger.info("Chart data cleared")
