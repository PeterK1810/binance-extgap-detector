"""Inventory Tracker for aggregating grid fills into positions."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from .models import Fill, Inventory, MMTradeResult

LOGGER = logging.getLogger("market_maker.inventory_tracker")


class InventoryTracker:
    """Tracks aggregated position from multiple grid fills.

    Uses VWAP (Volume Weighted Average Price) to calculate average entry price
    as orders fill at different levels.

    Example:
        >>> tracker = InventoryTracker("BTCUSDT")
        >>> tracker.add_fill(fill1)  # Buy 0.01 BTC @ 50000
        >>> tracker.add_fill(fill2)  # Buy 0.01 BTC @ 49500
        >>> print(tracker.current_inventory.average_entry_price)  # 49750 VWAP
    """

    def __init__(self, symbol: str):
        """Initialize inventory tracker.

        Args:
            symbol: Trading pair to track
        """
        self.symbol = symbol
        self.current_inventory: Optional[Inventory] = None
        self.closed_trades: List[MMTradeResult] = []

    def add_fill(self, fill: Fill) -> None:
        """Add a fill to the inventory.

        If no position exists, creates new inventory.
        If position exists in same direction, averages in (VWAP).

        Args:
            fill: Fill to add to inventory
        """
        if self.current_inventory is None:
            # Create new inventory
            side = "LONG" if fill.side == "BUY" else "SHORT"

            self.current_inventory = Inventory(
                symbol=self.symbol,
                side=side,
                total_quantity=fill.quantity,
                average_entry_price=fill.fill_price,
                total_notional_usd=fill.notional_usd,
                total_entry_fees=fill.maker_fee,
                fills=[fill],
                first_entry_time=fill.fill_time,
                last_entry_time=fill.fill_time
            )

            LOGGER.info(
                f"{self.symbol}: New {side} inventory, "
                f"qty={fill.quantity:.6f} @ {fill.fill_price:.2f}"
            )
            return

        inv = self.current_inventory

        # Check if same direction (adding to position)
        is_same_direction = (
            (inv.side == "LONG" and fill.side == "BUY") or
            (inv.side == "SHORT" and fill.side == "SELL")
        )

        if is_same_direction:
            # Add to position - recalculate VWAP
            # VWAP = (old_value + new_value) / (old_qty + new_qty)
            old_value = inv.average_entry_price * inv.total_quantity
            new_value = fill.fill_price * fill.quantity
            new_total_qty = inv.total_quantity + fill.quantity

            inv.average_entry_price = (old_value + new_value) / new_total_qty
            inv.total_quantity = new_total_qty
            inv.total_notional_usd += fill.notional_usd
            inv.total_entry_fees += fill.maker_fee
            inv.fills.append(fill)
            inv.last_entry_time = fill.fill_time

            LOGGER.info(
                f"{self.symbol}: Added to {inv.side}, "
                f"total_qty={inv.total_quantity:.6f}, "
                f"avg_price={inv.average_entry_price:.2f}, "
                f"fills={len(inv.fills)}"
            )
        else:
            # Opposite direction - this shouldn't happen with our strategy
            # (we cancel all orders on signal change before fills)
            LOGGER.warning(
                f"{self.symbol}: Unexpected opposite fill while {inv.side}, "
                f"ignoring {fill.side} fill"
            )

    def close_position(
        self,
        exit_price: float,
        exit_time: datetime,
        exit_fee: float,
        reason: str = "SIGNAL_REVERSAL"
    ) -> Optional[MMTradeResult]:
        """Close the current position and calculate P&L.

        Args:
            exit_price: Price to close at
            exit_time: When position was closed
            exit_fee: Exit fee (taker fee for market exit)
            reason: Close reason (SIGNAL_REVERSAL, 24H_EXPIRY, etc.)

        Returns:
            MMTradeResult with P&L details, or None if no position
        """
        if self.current_inventory is None:
            return None

        inv = self.current_inventory

        # Calculate gross P&L
        if inv.side == "LONG":
            # Long: profit if exit > entry
            gross_pnl = (exit_price - inv.average_entry_price) * inv.total_quantity
        else:  # SHORT
            # Short: profit if exit < entry
            gross_pnl = (inv.average_entry_price - exit_price) * inv.total_quantity

        # Calculate net P&L after all fees
        total_fees = inv.total_entry_fees + exit_fee
        realized_pnl = gross_pnl - total_fees

        # Determine status
        if realized_pnl > 0:
            status = "WIN"
        elif realized_pnl < 0:
            status = "LOSS"
        else:
            status = "BREAKEVEN"

        result = MMTradeResult(
            status=status,
            open_time=inv.first_entry_time,
            close_time=exit_time,
            symbol=self.symbol,
            side=inv.side,
            entry_price=inv.average_entry_price,
            exit_price=exit_price,
            position_size_usd=inv.total_notional_usd,
            position_size_qty=inv.total_quantity,
            num_fills=len(inv.fills),
            gross_pnl=gross_pnl,
            realized_pnl=realized_pnl,
            total_fees=total_fees,
            close_reason=reason,
            # Cumulative stats will be updated by pnl_calculator
            cumulative_wins=0,
            cumulative_losses=0,
            cumulative_pnl=0.0,
            cumulative_fees=0.0
        )

        self.closed_trades.append(result)

        LOGGER.info(
            f"{self.symbol}: Closed {inv.side} position, "
            f"entry={inv.average_entry_price:.2f}, exit={exit_price:.2f}, "
            f"qty={inv.total_quantity:.6f}, fills={len(inv.fills)}, "
            f"gross_pnl=${gross_pnl:.2f}, fees=${total_fees:.4f}, "
            f"realized_pnl=${realized_pnl:.2f} ({status})"
        )

        # Clear inventory
        self.current_inventory = None

        return result

    def has_position(self) -> bool:
        """Check if there's an open position.

        Returns:
            True if inventory exists
        """
        return self.current_inventory is not None

    def get_position_side(self) -> Optional[str]:
        """Get current position side.

        Returns:
            "LONG", "SHORT", or None
        """
        if self.current_inventory is None:
            return None
        return self.current_inventory.side

    def get_position_value(self, current_price: float) -> Optional[float]:
        """Get current position value at given price.

        Args:
            current_price: Current market price

        Returns:
            Position value in USD, or None if no position
        """
        if self.current_inventory is None:
            return None
        return self.current_inventory.total_quantity * current_price

    def get_unrealized_pnl(self, current_price: float) -> Optional[float]:
        """Calculate unrealized P&L at current price.

        Args:
            current_price: Current market price

        Returns:
            Unrealized P&L in USD, or None if no position
        """
        if self.current_inventory is None:
            return None

        inv = self.current_inventory

        if inv.side == "LONG":
            return (current_price - inv.average_entry_price) * inv.total_quantity
        else:  # SHORT
            return (inv.average_entry_price - current_price) * inv.total_quantity

    def get_stats(self) -> dict:
        """Get inventory statistics.

        Returns:
            Dictionary with inventory stats
        """
        stats = {
            "has_position": self.has_position(),
            "closed_trades": len(self.closed_trades),
        }

        if self.current_inventory:
            inv = self.current_inventory
            stats.update({
                "side": inv.side,
                "quantity": inv.total_quantity,
                "avg_entry": inv.average_entry_price,
                "notional_usd": inv.total_notional_usd,
                "num_fills": len(inv.fills),
                "entry_fees": inv.total_entry_fees,
            })

        return stats
