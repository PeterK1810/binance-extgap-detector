"""Market Maker Execution Layer - Main orchestrator for MM strategy."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING

from .models import GridConfig, GridState, Fill, MMTradeResult
from .atr_calculator import ATRCalculator
from .grid_manager import GridManager
from .fill_simulator import FillSimulator
from .inventory_tracker import InventoryTracker
from .pnl_calculator import MMPnLCalculator
from .csv_recorder import MMRecorderManager

if TYPE_CHECKING:
    from bots.indicators.binance_extgap_indicator_5m import (
        Candle,
        ExternalGapSymbolState,
        ExternalGapDetection,
    )

LOGGER = logging.getLogger("market_maker.execution_layer")


class MarketMakerExecutionLayer:
    """Orchestrates market maker execution with gap signal direction bias.

    Integrates:
    - Gap detection (from ExternalGapSymbolState)
    - ATR calculation (for grid spacing)
    - Grid management (order placement)
    - Fill simulation (candle-based fills)
    - Inventory tracking (VWAP position aggregation)
    - P&L calculation (maker/taker fees)
    - CSV logging (orders, fills, trades)

    Strategy flow:
    1. Gap signal detected -> cancel old grid, place new biased grid
    2. Each candle -> check for fills against pending orders
    3. Fill detected -> update inventory (VWAP), optionally refresh grid
    4. Opposite signal -> close position at market, reverse grid direction

    Example:
        >>> config = GridConfig(num_levels=3, notional_per_level=100)
        >>> layer = MarketMakerExecutionLayer(
        ...     symbol_state=gap_detector,
        ...     config=config,
        ...     data_dir=Path("data")
        ... )
        >>> for candle in candles:
        ...     await layer.process_candle(candle)
    """

    def __init__(
        self,
        symbol_state: "ExternalGapSymbolState",
        config: GridConfig,
        data_dir: Path,
        timeframe: str = "5m"
    ):
        """Initialize market maker execution layer.

        Args:
            symbol_state: Gap detection state machine
            config: Grid configuration
            data_dir: Directory for CSV output
            timeframe: Timeframe string for file naming
        """
        self.symbol_state = symbol_state
        self.config = config
        self.symbol = symbol_state.symbol

        # Initialize components
        self.atr_calculator = ATRCalculator(period=config.atr_period)
        self.grid_manager = GridManager(config)
        self.fill_simulator = FillSimulator(maker_fee_rate=config.maker_fee_rate)
        self.inventory_tracker = InventoryTracker(self.symbol)
        self.pnl_calculator = MMPnLCalculator(
            maker_fee_rate=config.maker_fee_rate,
            taker_fee_rate=config.taker_fee_rate
        )
        self.recorders = MMRecorderManager(data_dir, timeframe)

        # Grid state tracking
        self.grid_state = GridState()
        self.last_candle: Optional["Candle"] = None

        LOGGER.info(
            f"{self.symbol}: MM execution layer initialized, "
            f"levels={config.num_levels}, notional=${config.notional_per_level}/level, "
            f"ATR period={config.atr_period}"
        )

    def process_candle(self, candle: "Candle") -> Optional["ExternalGapDetection"]:
        """Process a new candle through the MM execution layer.

        This is the main entry point called for each new candle.

        Args:
            candle: Closed candle to process

        Returns:
            Gap detection if one occurred, None otherwise
        """
        # 1. Update ATR
        current_atr = self.atr_calculator.update(candle)

        # 2. Detect gap signal from existing gap detector
        gap = self.symbol_state.add_candle(candle)

        # 3. Handle gap signal if detected
        if gap is not None:
            self._handle_gap_signal(gap, candle, current_atr)

        # 4. Check for fills on this candle
        if self.grid_state.current_signal is not None:
            self._check_and_process_fills(candle, current_atr)

        self.last_candle = candle
        return gap

    def _handle_gap_signal(
        self,
        gap: "ExternalGapDetection",
        candle: "Candle",
        current_atr: Optional[float]
    ) -> None:
        """Handle a gap signal - potentially close position and place new grid.

        Args:
            gap: Detected gap
            candle: Current candle
            current_atr: Current ATR value
        """
        signal = gap.polarity  # "bullish" or "bearish"

        LOGGER.info(
            f"{self.symbol}: Gap signal - {signal.upper()}, "
            f"level={gap.gap_level:.2f}, "
            f"first_gap={gap.is_first_gap}, "
            f"seq=#{gap.sequence_number}"
        )

        # If this is a reversal (not first gap) and we have a position, close it
        if not gap.is_first_gap and self.inventory_tracker.has_position():
            self._close_position_on_reversal(candle)

        # Don't place grid without ATR
        if current_atr is None:
            LOGGER.warning(f"{self.symbol}: No ATR yet, skipping grid placement")
            return

        # Place new grid biased by signal
        # Use next candle open as reference price (simulate real entry)
        reference_price = candle.close  # Use close as estimate of next open

        cancelled, new_orders = self.grid_manager.handle_signal_change(
            signal=signal,
            symbol=self.symbol,
            reference_price=reference_price,
            atr=current_atr,
            timestamp=candle.close_time
        )

        # Record orders
        for order in new_orders:
            self.recorders.record_order(order)

        # Update grid state
        self.grid_state.current_signal = signal
        self.grid_state.signal_price = reference_price
        self.grid_state.signal_time = candle.close_time
        self.grid_state.atr_value = current_atr
        self.grid_state.active_orders = len(new_orders)

        LOGGER.info(
            f"{self.symbol}: Grid placed - {signal.upper()} bias, "
            f"{len(new_orders)} orders, ATR={current_atr:.2f}"
        )

    def _close_position_on_reversal(self, candle: "Candle") -> Optional[MMTradeResult]:
        """Close current position at market on signal reversal.

        Args:
            candle: Current candle (exit at close/open)

        Returns:
            Trade result if position was closed
        """
        if not self.inventory_tracker.has_position():
            return None

        inv = self.inventory_tracker.current_inventory
        exit_price = candle.close  # Market exit at current price

        # Calculate exit fee (taker for market exit)
        exit_notional = inv.total_quantity * exit_price
        exit_fee = exit_notional * self.config.taker_fee_rate

        # Close position
        result = self.inventory_tracker.close_position(
            exit_price=exit_price,
            exit_time=candle.close_time,
            exit_fee=exit_fee,
            reason="SIGNAL_REVERSAL"
        )

        if result:
            # Update cumulative stats
            result = self.pnl_calculator.record_trade(result)
            self.recorders.record_trade(result)

            LOGGER.info(
                f"{self.symbol}: Position closed on reversal, "
                f"pnl=${result.realized_pnl:.2f}, "
                f"fills={result.num_fills}"
            )

        return result

    def _check_and_process_fills(
        self,
        candle: "Candle",
        current_atr: Optional[float]
    ) -> List[Fill]:
        """Check for fills and process them.

        Args:
            candle: Current candle to check against
            current_atr: Current ATR for potential grid refresh

        Returns:
            List of fills that occurred
        """
        # Get pending orders from grid manager
        pending_orders = self.grid_manager.pending_orders

        # Check for fills
        fills = self.fill_simulator.check_fills(candle, pending_orders)

        for fill in fills:
            # Mark order as filled in grid manager
            self.grid_manager.mark_filled(
                order_id=fill.order_id,
                fill_price=fill.fill_price,
                filled_at=fill.fill_time,
                candle_time=fill.candle_time
            )

            # Update the order record
            if fill.order_id in self.grid_manager.filled_orders:
                self.recorders.record_order(
                    self.grid_manager.filled_orders[fill.order_id]
                )

            # Record fill
            self.recorders.record_fill(fill)
            self.pnl_calculator.record_fill(fill)

            # Add to inventory
            self.inventory_tracker.add_fill(fill)

            # Refresh grid level if enabled
            if self.config.refresh_on_fill and current_atr is not None:
                filled_order = self.grid_manager.filled_orders.get(fill.order_id)
                if filled_order:
                    new_order = self.grid_manager.refresh_filled_level(
                        filled_order=filled_order,
                        current_price=candle.close,
                        atr=current_atr,
                        timestamp=candle.close_time
                    )
                    if new_order:
                        self.recorders.record_order(new_order)

        # Update grid state
        self.grid_state.filled_orders += len(fills)
        self.grid_state.active_orders = len(self.grid_manager.pending_orders)

        return fills

    def close_position_manual(
        self,
        exit_price: float,
        reason: str = "MANUAL"
    ) -> Optional[MMTradeResult]:
        """Manually close current position.

        Args:
            exit_price: Price to close at
            reason: Close reason for logging

        Returns:
            Trade result if position was closed
        """
        if not self.inventory_tracker.has_position():
            return None

        inv = self.inventory_tracker.current_inventory
        exit_notional = inv.total_quantity * exit_price
        exit_fee = exit_notional * self.config.taker_fee_rate

        result = self.inventory_tracker.close_position(
            exit_price=exit_price,
            exit_time=datetime.now(timezone.utc),
            exit_fee=exit_fee,
            reason=reason
        )

        if result:
            result = self.pnl_calculator.record_trade(result)
            self.recorders.record_trade(result)
            self.grid_manager.cancel_all()

        return result

    def check_24h_expiry(self, candle: "Candle") -> Optional[MMTradeResult]:
        """Check and close position if open > 24 hours.

        Args:
            candle: Current candle for exit timing

        Returns:
            Trade result if position was expired
        """
        if not self.inventory_tracker.has_position():
            return None

        inv = self.inventory_tracker.current_inventory
        if inv.first_entry_time is None:
            return None

        age_seconds = (candle.close_time - inv.first_entry_time).total_seconds()

        if age_seconds >= 86400:  # 24 hours
            LOGGER.info(f"{self.symbol}: Position expired after 24h")
            return self.close_position_manual(
                exit_price=candle.close,
                reason="24H_EXPIRY"
            )

        return None

    def get_stats(self) -> dict:
        """Get comprehensive statistics.

        Returns:
            Dictionary with all component stats
        """
        return {
            "symbol": self.symbol,
            "grid_state": {
                "current_signal": self.grid_state.current_signal,
                "signal_price": self.grid_state.signal_price,
                "atr_value": self.grid_state.atr_value,
                "active_orders": self.grid_state.active_orders,
                "filled_orders": self.grid_state.filled_orders,
            },
            "atr": self.atr_calculator.get_state().__dict__,
            "grid": self.grid_manager.get_stats(),
            "inventory": self.inventory_tracker.get_stats(),
            "pnl": self.pnl_calculator.get_stats(),
        }

    def format_status(self) -> str:
        """Format current status for logging.

        Returns:
            Status string
        """
        inv = self.inventory_tracker
        grid = self.grid_manager

        pos_str = "No position"
        if inv.has_position():
            pos = inv.current_inventory
            pos_str = f"{pos.side} {pos.total_quantity:.6f} @ {pos.average_entry_price:.2f}"

        return (
            f"{self.symbol} | Signal: {self.grid_state.current_signal or 'None'} | "
            f"Position: {pos_str} | "
            f"Grid: {len(grid.pending_orders)} pending | "
            f"{self.pnl_calculator.format_summary()}"
        )
