"""Fill Simulator for simulating limit order fills based on candle data."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, TYPE_CHECKING

from .models import GridOrder, Fill

if TYPE_CHECKING:
    from bots.indicators.binance_extgap_indicator_5m import Candle

LOGGER = logging.getLogger("market_maker.fill_simulator")


class FillSimulator:
    """Simulates order fills based on candle OHLC data.

    Fill logic:
    - BID (buy limit) order fills if candle.low <= order.price
    - ASK (sell limit) order fills if candle.high >= order.price

    Fill price is the limit order price (simulating maker fill at limit).

    Example:
        >>> sim = FillSimulator(maker_fee_rate=0.00002)
        >>> fills = sim.check_fills(candle, pending_orders)
        >>> for fill in fills:
        ...     print(f"Filled {fill.side} @ {fill.fill_price}")
    """

    def __init__(self, maker_fee_rate: float = 0.00002):
        """Initialize fill simulator.

        Args:
            maker_fee_rate: Maker fee rate (0.00002 = 0.002%)
        """
        self.maker_fee_rate = maker_fee_rate
        self.total_fills = 0

    def check_fills(
        self,
        candle: "Candle",
        pending_orders: Dict[str, GridOrder]
    ) -> List[Fill]:
        """Check which pending orders would fill on this candle.

        Args:
            candle: OHLC candle to check against
            pending_orders: Dict of order_id -> GridOrder to check

        Returns:
            List of Fill objects for orders that filled
        """
        fills = []

        for order_id, order in list(pending_orders.items()):
            if order.status != "PENDING":
                continue

            filled = False
            fill_price = order.price

            if order.side == "BID":
                # Buy limit order fills if price drops to order level
                # candle.low is the lowest price reached during candle
                if candle.low <= order.price:
                    filled = True
                    LOGGER.debug(
                        f"BID fill: candle.low={candle.low:.2f} <= order.price={order.price:.2f}"
                    )
            else:  # ASK
                # Sell limit order fills if price rises to order level
                # candle.high is the highest price reached during candle
                if candle.high >= order.price:
                    filled = True
                    LOGGER.debug(
                        f"ASK fill: candle.high={candle.high:.2f} >= order.price={order.price:.2f}"
                    )

            if filled:
                # Calculate maker fee
                maker_fee = order.notional_usd * self.maker_fee_rate

                # Create Fill record
                fill = Fill(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side="BUY" if order.side == "BID" else "SELL",
                    fill_price=fill_price,
                    quantity=order.quantity,
                    notional_usd=order.notional_usd,
                    fill_time=datetime.now(timezone.utc),
                    candle_time=candle.close_time,
                    candle_high=candle.high,
                    candle_low=candle.low,
                    maker_fee=maker_fee,
                    is_entry=True  # Will be updated by inventory tracker if needed
                )

                fills.append(fill)
                self.total_fills += 1

                LOGGER.info(
                    f"Fill detected: {fill.side} {order.symbol} "
                    f"level={order.grid_level} @ {fill_price:.2f}, "
                    f"qty={order.quantity:.6f}, fee=${maker_fee:.4f}"
                )

        return fills

    def simulate_market_exit(
        self,
        symbol: str,
        side: str,
        quantity: float,
        exit_price: float,
        taker_fee_rate: float,
        candle: "Candle"
    ) -> Fill:
        """Simulate a market order exit (taker).

        Used when closing position on signal reversal.

        Args:
            symbol: Trading pair
            side: "BUY" (close short) or "SELL" (close long)
            quantity: Position quantity to close
            exit_price: Market exit price (usually candle open)
            taker_fee_rate: Taker fee rate for market orders
            candle: Current candle for timing

        Returns:
            Fill object for the exit
        """
        notional_usd = quantity * exit_price
        taker_fee = notional_usd * taker_fee_rate

        fill = Fill(
            order_id=f"exit-{datetime.now(timezone.utc).timestamp()}",
            symbol=symbol,
            side=side,
            fill_price=exit_price,
            quantity=quantity,
            notional_usd=notional_usd,
            fill_time=datetime.now(timezone.utc),
            candle_time=candle.close_time,
            candle_high=candle.high,
            candle_low=candle.low,
            maker_fee=taker_fee,  # Using maker_fee field for exit fee
            is_entry=False
        )

        LOGGER.info(
            f"Market exit: {side} {symbol} @ {exit_price:.2f}, "
            f"qty={quantity:.6f}, fee=${taker_fee:.4f}"
        )

        return fill

    def get_stats(self) -> Dict:
        """Get simulator statistics.

        Returns:
            Dictionary with fill stats
        """
        return {
            "total_fills": self.total_fills,
            "maker_fee_rate": self.maker_fee_rate,
        }
