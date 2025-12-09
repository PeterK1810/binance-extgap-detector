"""Market Maker Execution Layer for External Gap Detection.

This module adds market maker execution to the existing gap detection system:
- ATR-based grid of limit orders biased by signal direction
- Bullish gap -> BID orders only (buy below price)
- Bearish gap -> ASK orders only (sell above price)
- Simulated fills based on candle OHLC

Usage:
    python -m bots.market_maker.binance_mm_indicator --symbol BTCUSDT --timeframe 5m

Components:
    - models.py: Data structures (GridOrder, Fill, Inventory, GridConfig)
    - atr_calculator.py: Rolling ATR for grid spacing
    - grid_manager.py: Order placement and lifecycle
    - fill_simulator.py: Candle-based fill detection
    - inventory_tracker.py: VWAP position aggregation
    - pnl_calculator.py: P&L with maker/taker fees
    - csv_recorder.py: Order/fill/trade logging
    - mm_execution_layer.py: Main orchestrator
    - binance_mm_indicator.py: Entry point
"""

from .models import (
    GridOrder,
    Fill,
    Inventory,
    GridConfig,
    GridState,
    MMTradeResult,
)
from .atr_calculator import ATRCalculator
from .grid_manager import GridManager
from .fill_simulator import FillSimulator
from .inventory_tracker import InventoryTracker
from .pnl_calculator import MMPnLCalculator
from .csv_recorder import (
    MMOrderRecorder,
    MMFillRecorder,
    MMTradeRecorder,
    MMRecorderManager,
)
from .mm_execution_layer import MarketMakerExecutionLayer

__all__ = [
    # Models
    "GridOrder",
    "Fill",
    "Inventory",
    "GridConfig",
    "GridState",
    "MMTradeResult",
    # Components
    "ATRCalculator",
    "GridManager",
    "FillSimulator",
    "InventoryTracker",
    "MMPnLCalculator",
    # Recorders
    "MMOrderRecorder",
    "MMFillRecorder",
    "MMTradeRecorder",
    "MMRecorderManager",
    # Main
    "MarketMakerExecutionLayer",
]
