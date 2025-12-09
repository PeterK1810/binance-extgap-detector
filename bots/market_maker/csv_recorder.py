"""CSV Recorders for logging orders, fills, and trades."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .models import GridOrder, Fill, MMTradeResult

LOGGER = logging.getLogger("market_maker.csv_recorder")


class MMOrderRecorder:
    """Records grid orders to CSV file.

    Columns:
    - order_id, symbol, side, price, quantity, notional_usd
    - placed_at, grid_level, atr_multiplier, status
    - filled_at, fill_price, fill_candle_time
    """

    def __init__(self, output_path: Path):
        """Initialize order recorder.

        Args:
            output_path: Path to CSV file
        """
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write header if file doesn't exist
        if not self.output_path.exists():
            with open(self.output_path, "w") as f:
                f.write(
                    "order_id,symbol,side,price,quantity,notional_usd,"
                    "placed_at,grid_level,atr_multiplier,status,"
                    "filled_at,fill_price,fill_candle_time\n"
                )
            LOGGER.info(f"Created order log: {self.output_path}")

    def record_order(self, order: GridOrder) -> None:
        """Record an order (placement or status update).

        Args:
            order: GridOrder to record
        """
        filled_at = order.filled_at.isoformat() if order.filled_at else ""
        fill_price = f"{order.fill_price:.8f}" if order.fill_price else ""
        fill_candle = order.fill_candle_time.isoformat() if order.fill_candle_time else ""

        with open(self.output_path, "a") as f:
            f.write(
                f"{order.order_id},{order.symbol},{order.side},"
                f"{order.price:.8f},{order.quantity:.8f},{order.notional_usd:.2f},"
                f"{order.placed_at.isoformat()},{order.grid_level},{order.atr_multiplier:.2f},"
                f"{order.status},{filled_at},{fill_price},{fill_candle}\n"
            )


class MMFillRecorder:
    """Records fills to CSV file.

    Columns:
    - order_id, symbol, side, fill_price, quantity, notional_usd
    - fill_time, candle_time, candle_high, candle_low
    - maker_fee, is_entry
    """

    def __init__(self, output_path: Path):
        """Initialize fill recorder.

        Args:
            output_path: Path to CSV file
        """
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.output_path.exists():
            with open(self.output_path, "w") as f:
                f.write(
                    "order_id,symbol,side,fill_price,quantity,notional_usd,"
                    "fill_time,candle_time,candle_high,candle_low,"
                    "maker_fee,is_entry\n"
                )
            LOGGER.info(f"Created fill log: {self.output_path}")

    def record_fill(self, fill: Fill) -> None:
        """Record a fill event.

        Args:
            fill: Fill to record
        """
        with open(self.output_path, "a") as f:
            f.write(
                f"{fill.order_id},{fill.symbol},{fill.side},"
                f"{fill.fill_price:.8f},{fill.quantity:.8f},{fill.notional_usd:.2f},"
                f"{fill.fill_time.isoformat()},{fill.candle_time.isoformat()},"
                f"{fill.candle_high:.8f},{fill.candle_low:.8f},"
                f"{fill.maker_fee:.6f},{fill.is_entry}\n"
            )


class MMTradeRecorder:
    """Records completed trades (closed positions) to CSV file.

    Columns:
    - status, open_time, close_time, symbol, side
    - entry_price, exit_price, position_size_usd, position_size_qty
    - num_fills, gross_pnl, realized_pnl, total_fees, close_reason
    - cumulative_wins, cumulative_losses, cumulative_pnl, cumulative_fees
    """

    def __init__(self, output_path: Path):
        """Initialize trade recorder.

        Args:
            output_path: Path to CSV file
        """
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.output_path.exists():
            with open(self.output_path, "w") as f:
                f.write(
                    "status,open_time,close_time,symbol,side,"
                    "entry_price,exit_price,position_size_usd,position_size_qty,"
                    "num_fills,gross_pnl,realized_pnl,total_fees,close_reason,"
                    "cumulative_wins,cumulative_losses,cumulative_pnl,cumulative_fees\n"
                )
            LOGGER.info(f"Created trade log: {self.output_path}")

    def record_trade(self, result: MMTradeResult) -> None:
        """Record a completed trade.

        Args:
            result: Trade result to record
        """
        with open(self.output_path, "a") as f:
            f.write(
                f"{result.status},{result.open_time.isoformat()},"
                f"{result.close_time.isoformat()},{result.symbol},{result.side},"
                f"{result.entry_price:.8f},{result.exit_price:.8f},"
                f"{result.position_size_usd:.2f},{result.position_size_qty:.8f},"
                f"{result.num_fills},{result.gross_pnl:.4f},{result.realized_pnl:.4f},"
                f"{result.total_fees:.6f},{result.close_reason},"
                f"{result.cumulative_wins},{result.cumulative_losses},"
                f"{result.cumulative_pnl:.4f},{result.cumulative_fees:.6f}\n"
            )


class MMRecorderManager:
    """Manages all three recorders together.

    Convenience class for initializing and using all recorders.
    """

    def __init__(self, data_dir: Path, timeframe: str):
        """Initialize all recorders.

        Args:
            data_dir: Base directory for data files
            timeframe: Timeframe string for file naming (e.g., "5m")
        """
        self.order_recorder = MMOrderRecorder(
            data_dir / f"mm_orders_{timeframe}.csv"
        )
        self.fill_recorder = MMFillRecorder(
            data_dir / f"mm_fills_{timeframe}.csv"
        )
        self.trade_recorder = MMTradeRecorder(
            data_dir / f"mm_trades_{timeframe}.csv"
        )

        LOGGER.info(f"Initialized MM recorders in {data_dir}")

    def record_order(self, order: GridOrder) -> None:
        """Record an order."""
        self.order_recorder.record_order(order)

    def record_fill(self, fill: Fill) -> None:
        """Record a fill."""
        self.fill_recorder.record_fill(fill)

    def record_trade(self, result: MMTradeResult) -> None:
        """Record a trade."""
        self.trade_recorder.record_trade(result)
