"""Data models for Market Maker execution layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class GridConfig:
    """Configuration for the market maker grid.

    Attributes:
        num_levels: Number of grid orders per direction (e.g., 3)
        base_atr_multiplier: First level distance as ATR multiple (e.g., 0.5)
        atr_increment: Additional ATR distance per level (e.g., 0.5 -> 0.5, 1.0, 1.5)
        notional_per_level: USD value per grid order
        atr_period: Lookback period for ATR calculation
        maker_fee_rate: Maker fee rate (0.00002 = 0.002%)
        taker_fee_rate: Taker fee rate (0.0002 = 0.02%)
        refresh_on_fill: Whether to place new order when one fills
    """
    num_levels: int = 3
    base_atr_multiplier: float = 0.5
    atr_increment: float = 0.5
    notional_per_level: float = 100.0
    atr_period: int = 14
    maker_fee_rate: float = 0.00002  # 0.002%
    taker_fee_rate: float = 0.0002   # 0.02%
    refresh_on_fill: bool = True


@dataclass
class GridOrder:
    """A single limit order in the grid.

    Attributes:
        order_id: Unique identifier for tracking
        symbol: Trading pair (e.g., "BTCUSDT")
        side: "BID" (buy limit below) or "ASK" (sell limit above)
        price: Limit order price
        quantity: Order size in base currency
        notional_usd: Order size in USD
        placed_at: When order was created
        grid_level: Distance from mid-price (1, 2, 3...)
        atr_multiplier: ATR distance used for this level
        status: "PENDING", "FILLED", or "CANCELLED"
        filled_at: When order was filled (if filled)
        fill_price: Actual fill price (if filled)
        fill_candle_time: Candle close time when fill occurred
    """
    order_id: str
    symbol: str
    side: str  # "BID" or "ASK"
    price: float
    quantity: float
    notional_usd: float
    placed_at: datetime
    grid_level: int
    atr_multiplier: float
    status: str = "PENDING"  # "PENDING", "FILLED", "CANCELLED"
    filled_at: Optional[datetime] = None
    fill_price: Optional[float] = None
    fill_candle_time: Optional[datetime] = None


@dataclass
class Fill:
    """Record of a simulated order fill.

    Attributes:
        order_id: Reference to the GridOrder that was filled
        symbol: Trading pair
        side: "BUY" or "SELL"
        fill_price: Price at which fill occurred
        quantity: Filled quantity
        notional_usd: USD value of the fill
        fill_time: When fill was detected
        candle_time: Close time of candle that triggered fill
        candle_high: High of the fill candle
        candle_low: Low of the fill candle
        maker_fee: Fee paid for this fill (maker rate)
        is_entry: True if this fill adds to position
    """
    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    fill_price: float
    quantity: float
    notional_usd: float
    fill_time: datetime
    candle_time: datetime
    candle_high: float
    candle_low: float
    maker_fee: float
    is_entry: bool = True


@dataclass
class Inventory:
    """Aggregated position from multiple grid fills.

    Uses VWAP (Volume Weighted Average Price) for average entry.

    Attributes:
        symbol: Trading pair
        side: "LONG" or "SHORT"
        total_quantity: Sum of filled quantities
        average_entry_price: VWAP of all entries
        total_notional_usd: Total USD value of position
        total_entry_fees: Cumulative maker fees from entries
        fills: List of all fills contributing to this position
        first_entry_time: When first fill occurred
        last_entry_time: When most recent fill occurred
    """
    symbol: str
    side: str  # "LONG" or "SHORT"
    total_quantity: float
    average_entry_price: float
    total_notional_usd: float
    total_entry_fees: float
    fills: List[Fill] = field(default_factory=list)
    first_entry_time: Optional[datetime] = None
    last_entry_time: Optional[datetime] = None

    @property
    def num_fills(self) -> int:
        """Number of fills in this position."""
        return len(self.fills)


@dataclass
class MMTradeResult:
    """Result of a closed market maker position.

    Attributes:
        status: "WIN", "LOSS", or "BREAKEVEN"
        open_time: When first entry occurred
        close_time: When position was closed
        symbol: Trading pair
        side: "LONG" or "SHORT"
        entry_price: Average entry price (VWAP)
        exit_price: Exit price
        position_size_usd: Total notional USD
        position_size_qty: Total quantity
        num_fills: Number of grid fills for this position
        gross_pnl: P&L before fees
        realized_pnl: P&L after fees
        total_fees: Entry fees + exit fee
        close_reason: "SIGNAL_REVERSAL", "24H_EXPIRY", etc.
        cumulative_wins: Running total of winning trades
        cumulative_losses: Running total of losing trades
        cumulative_pnl: Running total P&L
        cumulative_fees: Running total fees paid
    """
    status: str  # "WIN", "LOSS", "BREAKEVEN"
    open_time: datetime
    close_time: datetime
    symbol: str
    side: str  # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    position_size_usd: float
    position_size_qty: float
    num_fills: int
    gross_pnl: float
    realized_pnl: float
    total_fees: float
    close_reason: str
    cumulative_wins: int = 0
    cumulative_losses: int = 0
    cumulative_pnl: float = 0.0
    cumulative_fees: float = 0.0


@dataclass
class GridState:
    """Current state of the market maker grid.

    Tracks signal direction and grid activity.

    Attributes:
        current_signal: "bullish", "bearish", or None
        signal_price: Price when signal was detected
        signal_time: When signal was detected
        atr_value: ATR at signal time (for grid spacing)
        active_orders: Number of pending orders
        filled_orders: Number of filled orders
    """
    current_signal: Optional[str] = None
    signal_price: Optional[float] = None
    signal_time: Optional[datetime] = None
    atr_value: Optional[float] = None
    active_orders: int = 0
    filled_orders: int = 0
