"""P&L Calculator for market maker with maker/taker fees."""

from __future__ import annotations

import logging
from typing import Dict, Any

from .models import Fill, MMTradeResult

LOGGER = logging.getLogger("market_maker.pnl_calculator")


class MMPnLCalculator:
    """P&L calculation with maker/taker fee handling.

    Tracks cumulative statistics across all trades:
    - Total P&L
    - Win/loss counts
    - Total fees paid
    - Trading volume

    Fee rates:
    - Maker (limit orders): 0.002% (0.00002)
    - Taker (market orders): 0.02% (0.0002)

    Example:
        >>> calc = MMPnLCalculator(maker_fee=0.00002, taker_fee=0.0002)
        >>> result = calc.record_trade(trade_result)
        >>> print(f"Win rate: {calc.win_rate:.1f}%")
    """

    def __init__(
        self,
        maker_fee_rate: float = 0.00002,
        taker_fee_rate: float = 0.0002
    ):
        """Initialize P&L calculator.

        Args:
            maker_fee_rate: Maker fee rate (0.00002 = 0.002%)
            taker_fee_rate: Taker fee rate (0.0002 = 0.02%)
        """
        self.maker_fee_rate = maker_fee_rate
        self.taker_fee_rate = taker_fee_rate

        # Cumulative statistics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.breakeven_trades = 0
        self.cumulative_pnl = 0.0
        self.cumulative_fees = 0.0
        self.cumulative_volume = 0.0
        self.total_fills = 0

        # Detailed tracking
        self.winning_pnls: list = []
        self.losing_pnls: list = []

    def calculate_entry_fee(self, notional_usd: float) -> float:
        """Calculate maker fee for entry fill.

        Args:
            notional_usd: Trade notional in USD

        Returns:
            Fee amount in USD
        """
        return notional_usd * self.maker_fee_rate

    def calculate_exit_fee(self, notional_usd: float, is_maker: bool = False) -> float:
        """Calculate fee for exit.

        Args:
            notional_usd: Trade notional in USD
            is_maker: True if exit is limit order, False for market

        Returns:
            Fee amount in USD
        """
        rate = self.maker_fee_rate if is_maker else self.taker_fee_rate
        return notional_usd * rate

    def record_fill(self, fill: Fill) -> None:
        """Record a fill for statistics.

        Args:
            fill: Fill to record
        """
        self.total_fills += 1
        self.cumulative_fees += fill.maker_fee

    def record_trade(self, result: MMTradeResult) -> MMTradeResult:
        """Record a closed trade and update cumulative stats.

        Args:
            result: Trade result to record

        Returns:
            Updated trade result with cumulative stats
        """
        self.total_trades += 1

        if result.status == "WIN":
            self.winning_trades += 1
            self.winning_pnls.append(result.realized_pnl)
        elif result.status == "LOSS":
            self.losing_trades += 1
            self.losing_pnls.append(result.realized_pnl)
        else:
            self.breakeven_trades += 1

        self.cumulative_pnl += result.realized_pnl
        self.cumulative_fees += result.total_fees
        self.cumulative_volume += result.position_size_usd

        # Update result with cumulative stats
        result.cumulative_wins = self.winning_trades
        result.cumulative_losses = self.losing_trades
        result.cumulative_pnl = self.cumulative_pnl
        result.cumulative_fees = self.cumulative_fees

        LOGGER.info(
            f"Trade recorded: {result.status}, "
            f"pnl=${result.realized_pnl:.2f}, "
            f"cumulative_pnl=${self.cumulative_pnl:.2f}, "
            f"win_rate={self.win_rate:.1f}%"
        )

        return result

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage.

        Returns:
            Win rate as percentage (0-100)
        """
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    @property
    def avg_win(self) -> float:
        """Calculate average winning trade P&L.

        Returns:
            Average win in USD
        """
        if not self.winning_pnls:
            return 0.0
        return sum(self.winning_pnls) / len(self.winning_pnls)

    @property
    def avg_loss(self) -> float:
        """Calculate average losing trade P&L (negative).

        Returns:
            Average loss in USD (negative value)
        """
        if not self.losing_pnls:
            return 0.0
        return sum(self.losing_pnls) / len(self.losing_pnls)

    @property
    def profit_factor(self) -> float:
        """Calculate profit factor (gross wins / gross losses).

        Returns:
            Profit factor (>1 is profitable)
        """
        total_wins = sum(self.winning_pnls) if self.winning_pnls else 0
        total_losses = abs(sum(self.losing_pnls)) if self.losing_pnls else 0

        if total_losses == 0:
            return float('inf') if total_wins > 0 else 0.0
        return total_wins / total_losses

    @property
    def avg_pnl_per_trade(self) -> float:
        """Calculate average P&L per trade.

        Returns:
            Average P&L in USD
        """
        if self.total_trades == 0:
            return 0.0
        return self.cumulative_pnl / self.total_trades

    @property
    def fee_ratio(self) -> float:
        """Calculate fees as percentage of volume.

        Returns:
            Fee ratio as decimal
        """
        if self.cumulative_volume == 0:
            return 0.0
        return self.cumulative_fees / self.cumulative_volume

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics.

        Returns:
            Dictionary with all stats
        """
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "win_rate": self.win_rate,
            "cumulative_pnl": self.cumulative_pnl,
            "cumulative_fees": self.cumulative_fees,
            "cumulative_volume": self.cumulative_volume,
            "total_fills": self.total_fills,
            "avg_pnl_per_trade": self.avg_pnl_per_trade,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "profit_factor": self.profit_factor,
            "fee_ratio": self.fee_ratio,
            "maker_fee_rate": self.maker_fee_rate,
            "taker_fee_rate": self.taker_fee_rate,
        }

    def format_summary(self) -> str:
        """Format a summary string for logging/display.

        Returns:
            Formatted summary string
        """
        return (
            f"Trades: {self.total_trades} "
            f"(W:{self.winning_trades}/L:{self.losing_trades}) | "
            f"Win Rate: {self.win_rate:.1f}% | "
            f"P&L: ${self.cumulative_pnl:.2f} | "
            f"Fees: ${self.cumulative_fees:.4f} | "
            f"Avg P&L: ${self.avg_pnl_per_trade:.2f}"
        )
