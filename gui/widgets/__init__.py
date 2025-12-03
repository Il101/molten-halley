"""
GUI Widgets Package

Professional PyQt6 widgets for real-time arbitrage monitoring.
"""

from gui.widgets.dashboard import Dashboard
from gui.widgets.pair_selector import PairSelector
from gui.widgets.monitor_table import MonitorTable
from gui.widgets.zscore_chart import ZScoreChart
from gui.widgets.connection_status import ConnectionStatus

__all__ = [
    'Dashboard',
    'PairSelector',
    'MonitorTable',
    'ZScoreChart',
    'ConnectionStatus'
]
