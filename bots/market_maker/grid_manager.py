"""Grid Manager for ATR-based limit order placement."""

from __future__ import annotations

import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .models import GridOrder, GridConfig

LOGGER = logging.getLogger("market_maker.grid_manager")


class GridManager:
    """Manages grid order placement and lifecycle.

    Places limit orders at ATR-based intervals in a single direction:
    - Bullish signal -> BID (buy) orders below current price
    - Bearish signal -> ASK (sell) orders above current price

    Grid levels are spaced using ATR multiples:
    - Level 1: price - (ATR * 0.5) for BID
    - Level 2: price - (ATR * 1.0) for BID
    - Level 3: price - (ATR * 1.5) for BID
    (Mirrored above price for ASK orders)

    Example:
        >>> gm = GridManager(config)
        >>> orders = gm.place_grid("BTCUSDT", 50000.0, "BID", atr=500.0, time)
        >>> # Places 3 buy orders at 49750, 49500, 49250
    """

    def __init__(self, config: GridConfig):
        """Initialize grid manager.

        Args:
            config: Grid configuration parameters
        """
        self.config = config
        self.pending_orders: Dict[str, GridOrder] = {}  # order_id -> order
        self.filled_orders: Dict[str, GridOrder] = {}   # order_id -> order
        self.cancelled_orders: Dict[str, GridOrder] = {}

    def calculate_grid_levels(
        self,
        reference_price: float,
        side: str,
        atr: float
    ) -> List[Tuple[int, float, float]]:
        """Calculate grid level prices based on ATR.

        Args:
            reference_price: Current price to build grid around
            side: "BID" (below price) or "ASK" (above price)
            atr: Current ATR value for spacing

        Returns:
            List of (level_number, price, notional_usd) tuples
        """
        levels = []

        for i in range(1, self.config.num_levels + 1):
            # Calculate ATR distance for this level
            # Level 1: base_atr_multiplier (0.5)
            # Level 2: base + increment (1.0)
            # Level 3: base + 2*increment (1.5)
            atr_distance = (
                self.config.base_atr_multiplier +
                (i - 1) * self.config.atr_increment
            )

            if side == "BID":
                # Buy orders below current price
                price = reference_price - (atr * atr_distance)
            else:  # ASK
                # Sell orders above current price
                price = reference_price + (atr * atr_distance)

            # Size scaling: closer levels get slightly more size
            # Level 1: 100%, Level 2: 90%, Level 3: 80%
            size_weight = 1.0 - (i - 1) * 0.1
            notional = self.config.notional_per_level * max(size_weight, 0.5)

            levels.append((i, price, notional))

        return levels

    def place_grid(
        self,
        symbol: str,
        reference_price: float,
        side: str,
        atr: float,
        placed_at: datetime
    ) -> List[GridOrder]:
        """Place grid orders on one side of the book.

        Args:
            symbol: Trading pair
            reference_price: Current price to build grid around
            side: "BID" (buy below) or "ASK" (sell above)
            atr: Current ATR for spacing calculation
            placed_at: Timestamp for order placement

        Returns:
            List of created GridOrder objects
        """
        levels = self.calculate_grid_levels(reference_price, side, atr)
        orders = []

        for level_num, price, notional in levels:
            quantity = notional / price
            atr_mult = (
                self.config.base_atr_multiplier +
                (level_num - 1) * self.config.atr_increment
            )

            order = GridOrder(
                order_id=str(uuid.uuid4()),
                symbol=symbol,
                side=side,
                price=price,
                quantity=quantity,
                notional_usd=notional,
                placed_at=placed_at,
                grid_level=level_num,
                atr_multiplier=atr_mult,
                status="PENDING"
            )

            self.pending_orders[order.order_id] = order
            orders.append(order)

            LOGGER.debug(
                f"Placed {side} order: level={level_num}, "
                f"price={price:.2f}, qty={quantity:.6f}, "
                f"notional=${notional:.2f}"
            )

        LOGGER.info(
            f"{symbol}: Placed {len(orders)} {side} orders, "
            f"prices: {[f'{o.price:.2f}' for o in orders]}"
        )

        return orders

    def cancel_side(self, side: str) -> List[GridOrder]:
        """Cancel all pending orders on one side.

        Args:
            side: "BID" or "ASK" to cancel

        Returns:
            List of cancelled orders
        """
        cancelled = []

        for order_id in list(self.pending_orders.keys()):
            order = self.pending_orders[order_id]
            if order.side == side and order.status == "PENDING":
                order.status = "CANCELLED"
                self.cancelled_orders[order_id] = order
                del self.pending_orders[order_id]
                cancelled.append(order)

        if cancelled:
            LOGGER.info(f"Cancelled {len(cancelled)} {side} orders")

        return cancelled

    def cancel_all(self) -> List[GridOrder]:
        """Cancel all pending orders.

        Returns:
            List of all cancelled orders
        """
        cancelled = []

        for order_id in list(self.pending_orders.keys()):
            order = self.pending_orders[order_id]
            if order.status == "PENDING":
                order.status = "CANCELLED"
                self.cancelled_orders[order_id] = order
                del self.pending_orders[order_id]
                cancelled.append(order)

        if cancelled:
            LOGGER.info(f"Cancelled all {len(cancelled)} pending orders")

        return cancelled

    def mark_filled(
        self,
        order_id: str,
        fill_price: float,
        filled_at: datetime,
        candle_time: datetime
    ) -> Optional[GridOrder]:
        """Mark an order as filled.

        Args:
            order_id: Order to mark filled
            fill_price: Price at which it filled
            filled_at: When fill was detected
            candle_time: Candle close time that triggered fill

        Returns:
            The filled order, or None if not found
        """
        if order_id not in self.pending_orders:
            return None

        order = self.pending_orders[order_id]
        order.status = "FILLED"
        order.fill_price = fill_price
        order.filled_at = filled_at
        order.fill_candle_time = candle_time

        # Move from pending to filled
        self.filled_orders[order_id] = order
        del self.pending_orders[order_id]

        LOGGER.info(
            f"Order filled: {order.side} level={order.grid_level}, "
            f"price={fill_price:.2f}, qty={order.quantity:.6f}"
        )

        return order

    def handle_signal_change(
        self,
        signal: str,
        symbol: str,
        reference_price: float,
        atr: float,
        timestamp: datetime
    ) -> Tuple[List[GridOrder], List[GridOrder]]:
        """Handle gap signal change - cancel old grid, place new biased grid.

        Bullish signal -> Cancel ASK orders, place BID orders only
        Bearish signal -> Cancel BID orders, place ASK orders only

        Args:
            signal: "bullish" or "bearish"
            symbol: Trading pair
            reference_price: Current price
            atr: Current ATR value
            timestamp: When signal was detected

        Returns:
            Tuple of (cancelled_orders, new_orders)
        """
        # Cancel all existing orders
        cancelled = self.cancel_all()

        # Determine order side based on signal
        if signal == "bullish":
            # Bullish = expect price to rise, place BID (buy) orders below
            order_side = "BID"
        else:  # bearish
            # Bearish = expect price to fall, place ASK (sell) orders above
            order_side = "ASK"

        # Place new grid
        new_orders = self.place_grid(
            symbol=symbol,
            reference_price=reference_price,
            side=order_side,
            atr=atr,
            placed_at=timestamp
        )

        LOGGER.info(
            f"{symbol}: Signal change to {signal.upper()}, "
            f"cancelled {len(cancelled)}, placed {len(new_orders)} {order_side} orders"
        )

        return cancelled, new_orders

    def refresh_filled_level(
        self,
        filled_order: GridOrder,
        current_price: float,
        atr: float,
        timestamp: datetime
    ) -> Optional[GridOrder]:
        """Replace a filled order with a new one at the same ATR distance.

        Only if refresh_on_fill is enabled in config.

        Args:
            filled_order: The order that was just filled
            current_price: Current market price
            atr: Current ATR value
            timestamp: Current time

        Returns:
            New order if created, None otherwise
        """
        if not self.config.refresh_on_fill:
            return None

        # Calculate new price at same ATR distance
        if filled_order.side == "BID":
            new_price = current_price - (atr * filled_order.atr_multiplier)
        else:
            new_price = current_price + (atr * filled_order.atr_multiplier)

        # Don't place if new price is worse than fill price
        if filled_order.side == "BID" and new_price >= filled_order.fill_price:
            LOGGER.debug(f"Skipping refresh: new BID price {new_price:.2f} >= fill {filled_order.fill_price:.2f}")
            return None
        if filled_order.side == "ASK" and new_price <= filled_order.fill_price:
            LOGGER.debug(f"Skipping refresh: new ASK price {new_price:.2f} <= fill {filled_order.fill_price:.2f}")
            return None

        # Create replacement order
        quantity = filled_order.notional_usd / new_price
        new_order = GridOrder(
            order_id=str(uuid.uuid4()),
            symbol=filled_order.symbol,
            side=filled_order.side,
            price=new_price,
            quantity=quantity,
            notional_usd=filled_order.notional_usd,
            placed_at=timestamp,
            grid_level=filled_order.grid_level,
            atr_multiplier=filled_order.atr_multiplier,
            status="PENDING"
        )

        self.pending_orders[new_order.order_id] = new_order

        LOGGER.info(
            f"Refreshed level {new_order.grid_level}: "
            f"new {new_order.side} @ {new_price:.2f}"
        )

        return new_order

    def get_pending_orders(self) -> List[GridOrder]:
        """Get all pending orders.

        Returns:
            List of pending GridOrder objects
        """
        return list(self.pending_orders.values())

    def get_stats(self) -> Dict:
        """Get grid statistics.

        Returns:
            Dictionary with grid stats
        """
        return {
            "pending_orders": len(self.pending_orders),
            "filled_orders": len(self.filled_orders),
            "cancelled_orders": len(self.cancelled_orders),
            "pending_bid": sum(1 for o in self.pending_orders.values() if o.side == "BID"),
            "pending_ask": sum(1 for o in self.pending_orders.values() if o.side == "ASK"),
        }
