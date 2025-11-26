#!/usr/bin/env python3
"""Live Binance Futures External Gap detector with simulated trading.

This script implements the "External Gap" detection algorithm based on tracking
candidate extremes (highest low, lowest high) since the last gap. A new gap forms
when price breaks beyond these candidates.

Strategy:
    * LONG entry when bullish gap detected (price breaks above lowest high)
    * SHORT entry when bearish gap detected (price breaks below highest low)
    * Reverses position on opposite gap signal (no SL/TP - pure trend following)
    * Entry at next candle open after gap detection

Features:
    * Streams klines from Binance Futures WebSocket
    * Detects external gaps using candidate tracking algorithm
    * Simulates trading with position reversal logic
    * Persists gaps and trades to CSV files
    * Sends Telegram notifications for gaps and trade updates

Usage:
    python paradex_extgap/binance_extgap_indicator_1h.py --symbol BTCUSDT --timeframe 1h
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import aiohttp
import websockets
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

# Load .env from parent directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

LOGGER = logging.getLogger("binance_extgap_indicator")

BINANCE_FUTURES_STREAM = "wss://fstream.binance.com/stream"
BINANCE_FUTURES_API = "https://fapi.binance.com"

# Default fee assumptions (expressed in decimal form)
DEFAULT_ENTRY_FEE_RATE = 0.0003  # 0.03% (0.02% fee + 0.01% slippage)
DEFAULT_EXIT_FEE_RATE = 0.0003  # 0.03% (0.02% fee + 0.01% slippage)
DEFAULT_NOTIONAL = 1000.0

# Timeframe in minutes for 1h indicator
TIMEFRAME_MINUTES = 60


# ════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════


def is_candle_aligned(open_time: datetime, timeframe_minutes: int) -> bool:
    """Check if candle open time aligns to timeframe boundary.

    Examples:
        For 15m timeframe: 10:00, 10:15, 10:30 are aligned
        For 1h timeframe: 10:00, 11:00, 12:00 are aligned

    Args:
        open_time: Candle open timestamp
        timeframe_minutes: Timeframe in minutes

    Returns:
        True if aligned to timeframe boundary
    """
    timestamp_ms = int(open_time.timestamp() * 1000)
    timeframe_ms = timeframe_minutes * 60 * 1000
    return (timestamp_ms % timeframe_ms) == 0


def get_current_stats_boundary(now: datetime, interval_minutes: int) -> datetime:
    """Get the current stats interval boundary (floored to interval).

    Examples:
        For 15m interval at 10:37 -> returns 10:30
        For 1h interval at 10:37 -> returns 10:00
        For 4h interval at 10:37 -> returns 08:00

    Args:
        now: Current UTC datetime
        interval_minutes: Stats interval in minutes

    Returns:
        Datetime floored to the interval boundary
    """
    # Convert to minutes since midnight UTC
    minutes_since_midnight = now.hour * 60 + now.minute
    # Floor to interval boundary
    boundary_minutes = (minutes_since_midnight // interval_minutes) * interval_minutes
    boundary_hour = boundary_minutes // 60
    boundary_minute = boundary_minutes % 60
    return now.replace(hour=boundary_hour, minute=boundary_minute, second=0, microsecond=0)


# ════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Candle:
    """Represents a closed kline."""

    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float

    @property
    def close_time(self) -> datetime:
        """Convert close timestamp to datetime."""
        return datetime.fromtimestamp(self.close_time_ms / 1000, tz=timezone.utc)

    @property
    def open_time(self) -> datetime:
        """Convert open timestamp to datetime."""
        return datetime.fromtimestamp(self.open_time_ms / 1000, tz=timezone.utc)


@dataclass
class ExternalGapDetection:
    """Detected external gap event."""

    detected_at: datetime
    symbol: str
    polarity: str  # "bullish" or "bearish"
    gap_level: float  # The candidate extreme that was broken
    gap_opening_bar_time: datetime  # When gap level was set
    detection_bar_time: datetime  # When gap was detected
    is_first_gap: bool = False  # True if first gap (no trade), False if reversal (trade)
    is_reversal: bool = False  # True if this gap reverses the previous trend
    sequence_number: int = 1  # Sequence number within current trend
    group_size_before_cleanup: int = 0  # Group size before cleanup (for debugging)
    prev_gap_level: float = 0.0  # Previous gap level (for trade close notification on reversal)
    prev_sequence_number: int = 0  # Previous sequence number (for trade close notification)


@dataclass
class ExtGapTrade:
    """Open trade position without SL/TP (exits only on reverse signal)."""

    symbol: str
    side: str  # "long" or "short"
    entry_time: datetime
    entry_price: float  # Next candle open after gap detection
    position_size_usd: float
    position_size_qty: float
    entry_fee: float  # Entry fee paid


@dataclass
class TradeResult:
    """Result of a closed trade."""

    status: str  # "WIN", "LOSS", "BREAKEVEN"
    open_time: datetime
    close_time: datetime
    market: str
    side: str  # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    position_size_usd: float
    position_size_qty: float
    gross_pnl: float  # Before fees
    realized_pnl: float  # After fees
    total_fees: float  # Entry + exit fees
    close_reason: str  # "REVERSE" or "MANUAL"
    cumulative_wins: int
    cumulative_losses: int
    cumulative_pnl: float
    cumulative_fees: float  # Total fees across all trades


@dataclass
class GapStatistics:
    """Tracks statistics for gap detection and trading performance."""

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    bullish_gaps: int = 0
    bearish_gaps: int = 0
    reversals: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    cumulative_pnl: float = 0.0
    cumulative_volume_usd: float = 0.0
    current_trend: Optional[str] = None
    current_sequence: int = 0
    gap_timestamps: List[datetime] = field(default_factory=list)
    winning_pnls: List[float] = field(default_factory=list)
    losing_pnls: List[float] = field(default_factory=list)

    @property
    def uptime_minutes(self) -> float:
        """Calculate uptime in minutes."""
        return (datetime.now(timezone.utc) - self.start_time).total_seconds() / 60

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    @property
    def avg_frequency_min(self) -> Optional[float]:
        """Calculate average time between gaps in minutes."""
        if len(self.gap_timestamps) < 2:
            return None
        total_time = (self.gap_timestamps[-1] - self.gap_timestamps[0]).total_seconds() / 60
        return total_time / (len(self.gap_timestamps) - 1) if len(self.gap_timestamps) > 1 else None

    @property
    def avg_winning_trade(self) -> float:
        """Calculate average winning trade P&L."""
        if not self.winning_pnls:
            return 0.0
        return sum(self.winning_pnls) / len(self.winning_pnls)

    @property
    def avg_losing_trade(self) -> float:
        """Calculate average losing trade P&L."""
        if not self.losing_pnls:
            return 0.0
        return sum(self.losing_pnls) / len(self.losing_pnls)

    def record_gap(self, polarity: str, is_reversal: bool, sequence: int) -> None:
        """Record a gap detection."""
        if polarity == "bullish":
            self.bullish_gaps += 1
        else:
            self.bearish_gaps += 1

        if is_reversal:
            self.reversals += 1

        self.current_trend = polarity
        self.current_sequence = sequence
        self.gap_timestamps.append(datetime.now(timezone.utc))

    def record_trade_close(self, result: TradeResult) -> None:
        """Record a closed trade."""
        self.total_trades += 1
        if result.status == "WIN":
            self.winning_trades += 1
            self.winning_pnls.append(result.realized_pnl)
        elif result.status == "LOSS":
            self.losing_trades += 1
            self.losing_pnls.append(result.realized_pnl)
        self.cumulative_pnl = result.cumulative_pnl
        self.cumulative_volume_usd += result.position_size_usd

    def to_dict(self) -> dict:
        """Convert to dictionary for notification."""
        return {
            "uptime_minutes": self.uptime_minutes,
            "bullish_gaps": self.bullish_gaps,
            "bearish_gaps": self.bearish_gaps,
            "reversals": self.reversals,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "cumulative_pnl": self.cumulative_pnl,
            "cumulative_volume_usd": self.cumulative_volume_usd,
            "current_trend": self.current_trend,
            "current_sequence": self.current_sequence,
            "avg_frequency_min": self.avg_frequency_min,
            "win_rate": self.win_rate,
            "avg_winning_trade": self.avg_winning_trade,
            "avg_losing_trade": self.avg_losing_trade,
        }


# ════════════════════════════════════════════════════════════════════════════
# EXTERNAL GAP SYMBOL STATE
# ════════════════════════════════════════════════════════════════════════════


class ExternalGapSymbolState:
    """Tracks external gaps for a single symbol using group-based candidate tracking.

    This implementation mirrors the PineScript '[THE] eG v2' algorithm:
    - Maintains a group of all bars since last gap
    - Calculates candidates from group extremes
    - On gap detection: cleans group and recalculates candidates

    External gaps are detected when price breaks beyond candidate extremes:
    - Bullish gap: Current low > bullish_candidate_high (lowest high since last gap)
    - Bearish gap: Current high < bearish_candidate_low (highest low since last gap)
    """

    def __init__(self, symbol: str):
        """Initialize symbol state.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
        """
        self.symbol = symbol
        self.candle_history: Deque[Candle] = deque(maxlen=500)

        # Group tracking (all bars since last gap) - V3 PineScript algorithm
        self.group_bar_times: Deque[datetime] = deque(maxlen=500)
        self.group_highs: Deque[float] = deque(maxlen=500)
        self.group_lows: Deque[float] = deque(maxlen=500)

        # Candidate tracking (extremes calculated from group)
        self.bearish_candidate_low: Optional[float] = None  # Highest low in group
        self.bearish_candidate_idx: Optional[datetime] = None
        self.bullish_candidate_high: Optional[float] = None  # Lowest high in group
        self.bullish_candidate_idx: Optional[datetime] = None

        # Gap tracking
        self.last_gap_level: Optional[float] = None
        self.last_gap_polarity: Optional[str] = None  # "bullish" or "bearish"
        self.last_gap_opening_time: Optional[datetime] = None

        # First gap tracking (for first-reversal entry strategy)
        self.first_gap_detected = False

        # Sequence tracking
        self.current_sequence_number: int = 0
        self.last_sequence_number: int = 0  # Previous sequence before reversal

        # Initialization flag (V3: waits for first gap to initialize)
        self.is_initialized = False

        # Candle validation tracking
        self.first_aligned_candle_received = False
        self.last_candle_time: Optional[datetime] = None

    def add_candle(self, candle: Candle) -> Optional[ExternalGapDetection]:
        """Process new closed candle and detect external gaps.

        Algorithm mirrors PineScript '[THE] eG v2':
        1. Add candle to group arrays
        2. If not initialized: find first gap using group extremes
        3. If initialized: check gap against candidates, then clean group and recalculate

        Args:
            candle: Closed candle to process

        Returns:
            ExternalGapDetection if gap detected, None otherwise
        """
        self.candle_history.append(candle)

        # Validate candle alignment
        if not self.first_aligned_candle_received:
            if is_candle_aligned(candle.open_time, TIMEFRAME_MINUTES):
                LOGGER.info(f"First aligned candle received: {candle.open_time}")
                self.first_aligned_candle_received = True
            else:
                LOGGER.warning(
                    f"Skipping misaligned candle: {candle.open_time} (waiting for {TIMEFRAME_MINUTES}m boundary)"
                )
                return None

        # Check for missing candles
        if self.last_candle_time is not None:
            expected_next = self.last_candle_time + timedelta(minutes=TIMEFRAME_MINUTES)
            if candle.open_time > expected_next:
                missing_count = int(
                    (candle.open_time - expected_next).total_seconds() / (TIMEFRAME_MINUTES * 60)
                )
                LOGGER.warning(
                    f"GAP IN DATA: {self.last_candle_time} -> {candle.open_time} ({missing_count} candles missing)"
                )
        self.last_candle_time = candle.open_time

        # Add current bar to group
        self.group_bar_times.append(candle.open_time)
        self.group_highs.append(candle.high)
        self.group_lows.append(candle.low)

        # ──────────────────────────────────────────────────────────────────────
        # INITIALIZATION PHASE: Detect first gap using group extremes
        # ──────────────────────────────────────────────────────────────────────

        if not self.is_initialized and len(self.group_highs) >= 2:
            # Find group extremes
            max_low = max(self.group_lows)
            min_high = min(self.group_highs)

            # Check if current bar creates a gap
            bearish_gap = candle.high < max_low
            bullish_gap = candle.low > min_high

            if not (bearish_gap or bullish_gap):
                return None

            # Gap detected! Initialize system
            is_bearish = bearish_gap
            polarity = "bearish" if is_bearish else "bullish"
            gap_level = max_low if is_bearish else min_high

            # Find which bar created the gap level
            gap_opening_bar_time = None
            for i in range(len(self.group_lows) - 1):
                if is_bearish and self.group_lows[i] == max_low:
                    gap_opening_bar_time = self.group_bar_times[i]
                    break
                if not is_bearish and self.group_highs[i] == min_high:
                    gap_opening_bar_time = self.group_bar_times[i]
                    break

            if gap_opening_bar_time is None:
                gap_opening_bar_time = self.group_bar_times[0]

            # Update gap tracking
            self.last_gap_level = gap_level
            self.last_gap_polarity = polarity
            self.last_gap_opening_time = gap_opening_bar_time

            # Initialize sequence
            self.current_sequence_number = 1
            self.first_gap_detected = True

            # Store group size before cleanup
            group_size_before = len(self.group_bar_times)

            # Initialize candidates from bars AFTER gap opening bar
            self.bearish_candidate_low = candle.low
            self.bearish_candidate_idx = candle.open_time
            self.bullish_candidate_high = candle.high
            self.bullish_candidate_idx = candle.open_time

            for i in range(len(self.group_bar_times)):
                if self.group_bar_times[i] > gap_opening_bar_time:
                    h = self.group_highs[i]
                    l = self.group_lows[i]
                    t = self.group_bar_times[i]

                    if l > self.bearish_candidate_low:
                        self.bearish_candidate_low = l
                        self.bearish_candidate_idx = t

                    if h < self.bullish_candidate_high:
                        self.bullish_candidate_high = h
                        self.bullish_candidate_idx = t

            self.is_initialized = True

            LOGGER.info(
                f"{self.symbol}: First {polarity} gap detected at {gap_level:.2f} - waiting for reversal to start trading"
            )

            return ExternalGapDetection(
                detected_at=datetime.now(timezone.utc),
                symbol=self.symbol,
                polarity=polarity,
                gap_level=gap_level,
                gap_opening_bar_time=gap_opening_bar_time,
                detection_bar_time=candle.close_time,
                is_first_gap=True,
                is_reversal=False,
                sequence_number=self.current_sequence_number,
                group_size_before_cleanup=group_size_before,
            )

        # ──────────────────────────────────────────────────────────────────────
        # NORMAL OPERATION: Check gap against candidates
        # ──────────────────────────────────────────────────────────────────────

        if self.is_initialized:
            # Update candidates if current bar has more extreme values
            if self.bearish_candidate_low is None or candle.low > self.bearish_candidate_low:
                self.bearish_candidate_low = candle.low
                self.bearish_candidate_idx = candle.open_time

            if self.bullish_candidate_high is None or candle.high < self.bullish_candidate_high:
                self.bullish_candidate_high = candle.high
                self.bullish_candidate_idx = candle.open_time

            # Check for new gap
            bearish_gap = candle.high < self.bearish_candidate_low
            bullish_gap = candle.low > self.bullish_candidate_high

            if not (bearish_gap or bullish_gap):
                return None

            # Gap detected!
            is_bearish = bearish_gap
            polarity = "bearish" if is_bearish else "bullish"
            gap_level = self.bearish_candidate_low if is_bearish else self.bullish_candidate_high
            gap_opening_bar_time = self.bearish_candidate_idx if is_bearish else self.bullish_candidate_idx

            # Check if reversal
            is_reversal = self.last_gap_polarity is not None and self.last_gap_polarity != polarity

            if is_reversal:
                self.last_sequence_number = self.current_sequence_number
                self.current_sequence_number = 1  # Reset sequence
                LOGGER.info(
                    f"{self.symbol}: {polarity.upper()} reversal gap detected at {gap_level:.2f} - preparing entry"
                )
            else:
                self.current_sequence_number += 1  # Increment sequence
                LOGGER.info(
                    f"{self.symbol}: {polarity.upper()} gap #{self.current_sequence_number} detected at {gap_level:.2f}"
                )

            # Store group size before cleanup (for analysis)
            group_size_before = len(self.group_bar_times)

            # Capture previous values BEFORE updating (for trade close notification on reversal)
            prev_gap_level = self.last_gap_level or 0.0
            prev_sequence = self.last_sequence_number if is_reversal else 0

            # Update gap tracking
            self.last_gap_level = gap_level
            self.last_gap_polarity = polarity
            self.last_gap_opening_time = gap_opening_bar_time

            # Clean up group: remove bars <= gap opening bar
            while len(self.group_bar_times) > 0 and self.group_bar_times[0] <= gap_opening_bar_time:
                self.group_bar_times.popleft()
                self.group_highs.popleft()
                self.group_lows.popleft()

            # Recalculate candidates from remaining group
            if len(self.group_highs) > 0:
                self.bearish_candidate_low = max(self.group_lows)
                self.bullish_candidate_high = min(self.group_highs)

                # Find indices of candidates
                for i in range(len(self.group_lows)):
                    if self.group_lows[i] == self.bearish_candidate_low:
                        self.bearish_candidate_idx = self.group_bar_times[i]
                    if self.group_highs[i] == self.bullish_candidate_high:
                        self.bullish_candidate_idx = self.group_bar_times[i]
            else:
                # Group is empty, use current candle
                self.bearish_candidate_low = candle.low
                self.bearish_candidate_idx = candle.open_time
                self.bullish_candidate_high = candle.high
                self.bullish_candidate_idx = candle.open_time

            return ExternalGapDetection(
                detected_at=datetime.now(timezone.utc),
                symbol=self.symbol,
                polarity=polarity,
                gap_level=gap_level,
                gap_opening_bar_time=gap_opening_bar_time,
                detection_bar_time=candle.close_time,
                is_first_gap=False,
                is_reversal=is_reversal,
                sequence_number=self.current_sequence_number,
                group_size_before_cleanup=group_size_before,
                prev_gap_level=prev_gap_level,
                prev_sequence_number=prev_sequence,
            )

        return None


# ════════════════════════════════════════════════════════════════════════════
# TRADE MANAGER (Reverse-on-Signal)
# ════════════════════════════════════════════════════════════════════════════


class ExtGapTradeManager:
    """Manages single position with reverse-on-signal logic (no SL/TP).

    Strategy:
        - One position at a time per symbol
        - Enter long on bullish gap, short on bearish gap
        - Close and reverse when opposite gap appears
        - Entry at next candle open after gap detection
        - No stop loss or take profit levels
    """

    def __init__(
        self, notional_usd: float, entry_fee_rate: float, exit_fee_rate: float
    ):
        """Initialize trade manager.

        Args:
            notional_usd: Position size in USD
            entry_fee_rate: Entry fee rate (decimal, e.g., 0.0002 = 0.02%)
            exit_fee_rate: Exit fee rate (decimal, e.g., 0.0002 = 0.02%)
        """
        self.notional_usd = notional_usd
        self.entry_fee_rate = entry_fee_rate
        self.exit_fee_rate = exit_fee_rate

        # Position tracking (one position per symbol)
        self.current_positions: Dict[str, ExtGapTrade] = {}

        # Cumulative statistics
        self.cumulative_pnl = 0.0
        self.cumulative_volume = 0.0
        self.total_fees = 0.0
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0

    def open_or_reverse(
        self, symbol: str, side: str, entry_price: float, entry_time: datetime
    ) -> Tuple[Optional[TradeResult], ExtGapTrade]:
        """Close current position (if opposite side) and open new position.

        Args:
            symbol: Trading symbol
            side: "long" or "short"
            entry_price: Entry price (next candle open)
            entry_time: Entry timestamp

        Returns:
            Tuple of (closed_trade_result, new_trade)
        """
        closed_trade = None

        # Close existing position if opposite side
        if symbol in self.current_positions:
            current_trade = self.current_positions[symbol]
            if current_trade.side != side:
                closed_trade = self._close_position(
                    current_trade, entry_price, entry_time, "REVERSE"
                )
            else:
                # Same side - just log and don't open duplicate
                LOGGER.warning(
                    f"{symbol}: Ignoring {side} signal - already in {current_trade.side} position"
                )
                # Return None for closed, current position for new
                return (None, current_trade)

        # Open new position
        position_size_qty = self.notional_usd / entry_price
        entry_fee = self.notional_usd * self.entry_fee_rate

        new_trade = ExtGapTrade(
            symbol=symbol,
            side=side,
            entry_time=entry_time,
            entry_price=entry_price,
            position_size_usd=self.notional_usd,
            position_size_qty=position_size_qty,
            entry_fee=entry_fee,
        )

        self.current_positions[symbol] = new_trade
        self.cumulative_volume += self.notional_usd
        self.total_fees += entry_fee

        LOGGER.info(
            f"{symbol}: Opened {side.upper()} position at {entry_price:.2f} ({position_size_qty:.6f} qty)"
        )

        return closed_trade, new_trade

    def _close_position(
        self, trade: ExtGapTrade, exit_price: float, exit_time: datetime, reason: str
    ) -> TradeResult:
        """Close position at exit price.

        Args:
            trade: Trade to close
            exit_price: Exit price
            exit_time: Exit timestamp
            reason: Close reason ("REVERSE" or "MANUAL")

        Returns:
            TradeResult with PnL and statistics
        """
        # Calculate PnL based on side
        if trade.side == "long":
            pnl_pct = (exit_price - trade.entry_price) / trade.entry_price
        else:  # short
            pnl_pct = (trade.entry_price - exit_price) / trade.entry_price

        gross_pnl = trade.position_size_usd * pnl_pct
        exit_fee = trade.position_size_usd * self.exit_fee_rate
        total_fees = trade.entry_fee + exit_fee
        net_pnl = gross_pnl - total_fees

        # Update statistics
        self.cumulative_pnl += net_pnl
        self.cumulative_volume += trade.position_size_usd
        self.total_fees += total_fees  # Track both entry and exit fees
        self.trade_count += 1

        if net_pnl > 0:
            self.win_count += 1
            status = "WIN"
        elif net_pnl < 0:
            self.loss_count += 1
            status = "LOSS"
        else:
            status = "BREAKEVEN"

        result = TradeResult(
            status=status,
            open_time=trade.entry_time,
            close_time=exit_time,
            market=trade.symbol,
            side=trade.side.upper(),
            entry_price=trade.entry_price,
            exit_price=exit_price,
            position_size_usd=trade.position_size_usd,
            position_size_qty=trade.position_size_qty,
            gross_pnl=gross_pnl,
            realized_pnl=net_pnl,
            total_fees=total_fees,
            close_reason=reason,
            cumulative_wins=self.win_count,
            cumulative_losses=self.loss_count,
            cumulative_pnl=self.cumulative_pnl,
            cumulative_fees=self.total_fees,
        )

        # Remove from current positions
        del self.current_positions[trade.symbol]

        LOGGER.info(
            f"{trade.symbol}: Closed {trade.side.upper()} position - PnL: ${net_pnl:.2f} ({reason})"
        )

        return result

    def get_current_position(self, symbol: str) -> Optional[ExtGapTrade]:
        """Get current position for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Current position or None
        """
        return self.current_positions.get(symbol)

    def check_24h_expiry(
        self, symbol: str, current_time: datetime, current_price: float
    ) -> Optional[TradeResult]:
        """Check if position has been open >= 24 hours and close if needed.

        Args:
            symbol: Trading symbol
            current_time: Current timestamp
            current_price: Current price for exit

        Returns:
            TradeResult if position was closed due to 24h expiry, None otherwise
        """
        if symbol not in self.current_positions:
            return None

        trade = self.current_positions[symbol]
        time_diff = current_time - trade.entry_time

        # Check if 24 hours (86400 seconds) have passed
        if time_diff.total_seconds() >= 86400:
            LOGGER.info(
                f"{symbol}: 24-hour expiry reached - closing {trade.side.upper()} position"
            )
            return self._close_position(trade, current_price, current_time, "24H_EXPIRY")

        return None

    def close_all_positions(self, exit_price_map: Dict[str, float]) -> List[TradeResult]:
        """Close all open positions (used on shutdown).

        Args:
            exit_price_map: Map of symbol -> current price for exit

        Returns:
            List of trade results
        """
        results = []
        exit_time = datetime.now(timezone.utc)

        for symbol, trade in list(self.current_positions.items()):
            exit_price = exit_price_map.get(symbol, trade.entry_price)
            result = self._close_position(trade, exit_price, exit_time, "MANUAL")
            results.append(result)

        return results


# ════════════════════════════════════════════════════════════════════════════
# CSV RECORDERS
# ════════════════════════════════════════════════════════════════════════════


class ExtGapRecorder:
    """Records external gap detections to CSV."""

    def __init__(self, output_path: Path):
        """Initialize gap recorder.

        Args:
            output_path: Path to output CSV file
        """
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write header if file doesn't exist
        if not self.output_path.exists():
            with open(self.output_path, "w") as f:
                f.write(
                    "detected_at_utc,symbol,polarity,gap_level,gap_opening_bar_time,detection_bar_time\n"
                )

    def record(self, gap: ExternalGapDetection) -> None:
        """Record gap detection to CSV.

        Args:
            gap: Gap detection to record
        """
        with open(self.output_path, "a") as f:
            f.write(
                f"{gap.detected_at.isoformat()},"
                f"{gap.symbol},"
                f"{gap.polarity},"
                f"{gap.gap_level:.8f},"
                f"{gap.gap_opening_bar_time.isoformat()},"
                f"{gap.detection_bar_time.isoformat()}\n"
            )
        LOGGER.debug(f"Recorded {gap.polarity} gap for {gap.symbol}")


class TradeRecorder:
    """Records trade results to CSV."""

    def __init__(self, output_path: Path):
        """Initialize trade recorder.

        Args:
            output_path: Path to output CSV file
        """
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write header if file doesn't exist
        if not self.output_path.exists():
            with open(self.output_path, "w") as f:
                f.write(
                    "Status,Open Time,Close Time,Market,Side,Entry Price,Exit Price,"
                    "Position Size ($),Position Size (Qty),Gross P&L,Realized P&L,"
                    "Total Fees,Close Reason,Cumulative Wins,Cumulative Losses,Cumulative P&L,Cumulative Fees\n"
                )

    def record(self, result: TradeResult) -> None:
        """Record trade result to CSV.

        Args:
            result: Trade result to record
        """
        with open(self.output_path, "a") as f:
            f.write(
                f"{result.status},"
                f"{result.open_time.isoformat()},"
                f"{result.close_time.isoformat()},"
                f"{result.market},"
                f"{result.side},"
                f"{result.entry_price:.8f},"
                f"{result.exit_price:.8f},"
                f"{result.position_size_usd:.2f},"
                f"{result.position_size_qty:.8f},"
                f"{result.gross_pnl:.2f},"
                f"{result.realized_pnl:.2f},"
                f"{result.total_fees:.2f},"
                f"{result.close_reason},"
                f"{result.cumulative_wins},"
                f"{result.cumulative_losses},"
                f"{result.cumulative_pnl:.2f},"
                f"{result.cumulative_fees:.2f}\n"
            )
        LOGGER.debug(f"Recorded {result.status} trade for {result.market}")


# ════════════════════════════════════════════════════════════════════════════
# TELEGRAM NOTIFICATIONS
# ════════════════════════════════════════════════════════════════════════════


class TelegramExtGapNotifier:
    """Sends Telegram notifications for external gaps and trades."""

    def __init__(self, bot_token: str, chat_ids: List[str], instance_id: str, timeframe: str):
        """Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot API token
            chat_ids: List of chat IDs to send notifications to
            instance_id: Instance identifier (e.g., "LOCAL", "AWS")
            timeframe: Timeframe string (e.g., "1m", "5m", "15m", "1h")
        """
        self.bot = Bot(token=bot_token)
        self.chat_ids = chat_ids
        self.instance_id = instance_id
        self.timeframe = timeframe

    @classmethod
    def from_env(cls, timeframe: str) -> Optional["TelegramExtGapNotifier"]:
        """Create notifier from environment variables.

        Checks for timeframe-specific variables first, falls back to DETECTOR, then generic.
        - TELEGRAM_BOT_TOKEN_EXTGAP_{TIMEFRAME} or TELEGRAM_BOT_TOKEN_EXTGAP_DETECTOR or TELEGRAM_BOT_TOKEN
        - TELEGRAM_CHAT_IDS_EXTGAP_{TIMEFRAME} or TELEGRAM_CHAT_IDS_EXTGAP_DETECTOR or TELEGRAM_CHAT_IDS
        - INSTANCE_ID (defaults to "LOCAL")

        Args:
            timeframe: Timeframe string (e.g., "1m", "5m", "15m", "1h")

        Returns:
            TelegramExtGapNotifier instance or None if credentials missing
        """
        # Use 1H credentials for 1H timeframe
        bot_token = (
            os.getenv("TELEGRAM_BOT_TOKEN_EXTGAP_1H")
            or os.getenv("TELEGRAM_BOT_TOKEN")
        )
        chat_ids_str = (
            os.getenv("TELEGRAM_CHAT_IDS_EXTGAP_1H")
            or os.getenv("TELEGRAM_CHAT_IDS")
        )
        instance_id = os.getenv("INSTANCE_ID", "LOCAL")

        if not bot_token or not chat_ids_str:
            LOGGER.warning(
                "Telegram credentials not found in environment - notifications disabled"
            )
            return None

        chat_ids = [cid.strip() for cid in chat_ids_str.split(",") if cid.strip()]

        if not chat_ids:
            LOGGER.warning("No valid Telegram chat IDs found - notifications disabled")
            return None

        LOGGER.info(f"Telegram notifications enabled for {len(chat_ids)} chat(s)")
        return cls(bot_token, chat_ids, instance_id, timeframe)

    async def _send_message(self, message: str) -> None:
        """Send message to all configured chat IDs.

        Args:
            message: Message text to send
        """
        for chat_id in self.chat_ids:
            try:
                await self.bot.send_message(
                    chat_id=chat_id, text=message, parse_mode="HTML"
                )
            except TelegramError as e:
                LOGGER.error(f"Failed to send Telegram message to {chat_id}: {e}")

    async def notify_status(self, status: str, reason: str = "", symbol: str = "BTCUSDT", stats_interval: str = "4h") -> None:
        """Send status notification (start/stop).

        Args:
            status: "started" or "stopped"
            reason: Optional reason for status change
            symbol: Trading symbol
            stats_interval: Statistics notification interval
        """
        if status == "started":
            current_time = datetime.now(timezone.utc).strftime("%H:%M:%S")
            message = (
                f"🚀 <b>BOT V3 REPLIT DÉMARRÉ - {symbol}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {current_time} UTC\n"
                f"📊 Version: <b>V3 Replit (PineScript Algorithm)</b>\n"
                f"🖥️ Instance: <b>{self.instance_id}</b>\n"
                f"⏱️ Timeframe: <b>{self.timeframe}</b>\n"
                f"📈 Stats interval: <b>{stats_interval}</b>\n"
                f"🔍 Statut: <b>Surveillance active</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Détection des gaps externes en cours..."
            )
        else:
            current_time = datetime.now(timezone.utc).strftime("%H:%M:%S")
            message = (
                f"🛑 <b>BOT INDICATOR ARRÊTÉ</b>\n"
                f"Instance: {self.instance_id}"
            )
            if reason:
                message += f"\nRaison: {reason}"

        await self._send_message(message)

    async def notify_gap_detection(
        self, gap: ExternalGapDetection, is_first_gap: bool = False, sequence_number: int = 1
    ) -> None:
        """Send gap detection notification with candle details.

        Args:
            gap: Detected gap
            is_first_gap: Whether this is the first gap (no trade) or reversal (trade)
            sequence_number: Sequence number within current trend
        """
        emoji = "⬆️" if gap.polarity == "bullish" else "⬇️"

        if is_first_gap:
            message = (
                f"🚀 <b>PREMIER GAP DÉTECTÉ - {gap.symbol}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {gap.detection_bar_time.strftime('%H:%M:%S')} UTC\n"
                f"📊 Polarité: <b>{gap.polarity.upper()} #{sequence_number}</b> {emoji}\n"
                f"💰 Niveau: <b>{gap.gap_level:,.2f} USDT</b>\n"
                f"🕒 Barre ouverture: {gap.gap_opening_bar_time.strftime('%H:%M:%S')}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ Pas de trade - attente inversion"
            )
        else:
            # Continuation gap - simpler format matching user's example
            message = (
                f"📊 <b>GAP {gap.polarity.upper()} #{sequence_number} DÉTECTÉ - {gap.symbol}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {gap.detection_bar_time.strftime('%H:%M:%S')} UTC\n"
                f"💰 Niveau: <b>{gap.gap_level:,.2f} USDT</b>\n"
                f"📈 Séquence: <b>{gap.polarity.upper()} #{sequence_number}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
        await self._send_message(message)

    async def notify_trade_open(self, trade: ExtGapTrade, gap_level: float, sequence_number: int = 1) -> None:
        """Send trade open notification with gap details.

        Args:
            trade: Opened trade
            gap_level: Gap level that triggered entry
            sequence_number: Sequence number for this trade
        """
        side_text = "LONG" if trade.side == "long" else "SHORT"
        emoji = "📈" if trade.side == "long" else "📉"

        message = (
            f"{emoji} <b>ENTRÉE {side_text} #{sequence_number} - {trade.symbol}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {trade.entry_time.strftime('%H:%M:%S')} UTC\n"
            f"💰 Prix d'entrée: <b>{trade.entry_price:,.2f} USDT</b>\n"
            f"📊 Niveau gap: {gap_level:,.2f} USDT\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Position: ${trade.position_size_usd:.2f}\n"
            f"🔢 Quantité: {trade.position_size_qty:.6f} BTC\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Sortie: Reversal sur gap opposé"
        )
        await self._send_message(message)

    async def notify_trade_close(
        self,
        result: TradeResult,
        prev_sequence: int = 0,
        new_sequence: int = 1,
        new_polarity: str = "unknown",
        new_gap_level: float = 0.0,
        prev_gap_level: float = 0.0,
        new_entry_price: float = 0.0,
    ) -> None:
        """Send trade close notification.

        Args:
            result: Trade result
            prev_sequence: Previous sequence number
            new_sequence: New sequence number after reversal
            new_polarity: New polarity after reversal
            new_gap_level: New gap level after reversal
            prev_gap_level: Previous gap level
            new_entry_price: Entry price of new position
        """
        status_emoji = "✅" if result.status == "WIN" else "❌"
        pnl_sign = "+" if result.realized_pnl >= 0 else ""
        pnl_pct = (result.realized_pnl / result.position_size_usd) * 100

        # Determine side and polarity emojis
        old_polarity = "BEARISH" if result.side == "SHORT" else "BULLISH"
        old_emoji = "🔴" if result.side == "SHORT" else "🟢"
        new_emoji = "🟢" if new_polarity == "bullish" else "🔴"

        # Calculate quantity in BTC
        qty_btc = result.position_size_usd / result.entry_price

        message = (
            f"🔄 <b>INVERSION DE TENDANCE - {result.market}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {result.close_time.strftime('%H:%M:%S')} UTC\n"
            f"{old_emoji} <b>{old_polarity} #{prev_sequence}</b> → {new_emoji} <b>{new_polarity.upper()} #{new_sequence}</b>\n"
            f"💰 Nouveau niveau: <b>{new_gap_level:,.2f} USDT</b>\n"
            f"📊 Gap précédent: {prev_gap_level:,.2f} ({old_polarity.lower()} #{prev_sequence})\n"
            f"\n"
            f"💰 <b>P&L Position Fermée:</b>\n"
            f"  {status_emoji} {result.side}: <b>{pnl_sign}{result.realized_pnl:.2f} USD ({pnl_sign}{pnl_pct:.2f}%)</b>\n"
            f"  📊 Entrée: {result.entry_price:,.2f} → Sortie: {result.exit_price:,.2f}\n"
            f"  🔢 Quantité: {qty_btc:.6f} BTC\n"
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Prix d'entrée nouvelle position: <b>{new_entry_price:,.2f} USDT</b>"
        )
        await self._send_message(message)

    async def notify_stats(self, symbol: str, stats_interval: str, stats: dict) -> None:
        """Send periodic statistics notification.

        Args:
            symbol: Trading symbol
            stats_interval: Stats interval string (e.g., "10m", "30m")
            stats: Statistics dictionary from GapStatistics.to_dict()
        """
        # Format uptime
        uptime_min = stats['uptime_minutes']
        if uptime_min < 60:
            uptime_text = f"{uptime_min:.0f}m"
        elif uptime_min < 1440:
            uptime_text = f"{uptime_min/60:.1f}h"
        else:
            uptime_text = f"{uptime_min/1440:.1f}d"

        # P&L emoji
        pnl = stats['cumulative_pnl']
        pnl_emoji = "✅" if pnl > 0 else ("❌" if pnl < 0 else "➖")

        # Trend display
        current_trend = stats['current_trend']
        current_seq = stats['current_sequence']

        if current_trend == "bullish":
            trend_text = f"🟢 <b>BULLISH #{current_seq}</b>"
        elif current_trend == "bearish":
            trend_text = f"🔴 <b>BEARISH #{current_seq}</b>"
        else:
            trend_text = "⚪ <b>N/A</b>"

        # Frequency text
        freq = stats['avg_frequency_min']
        freq_text = f"{freq:.1f} min" if freq else "N/A"

        message = (
            f"📊 <b>STATISTIQUES ({stats_interval}) - {symbol}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {datetime.now(timezone.utc).strftime('%H:%M')} UTC\n"
            f"⏱️ Timeframe: <b>{self.timeframe}</b>\n"
            f"⏳ Uptime: <b>{uptime_text}</b>\n"
            f"\n"
            f"<b>📈 GAP STATISTICS:</b>\n"
            f"⬆️ Gaps bullish: <b>{stats['bullish_gaps']}</b>\n"
            f"⬇️ Gaps bearish: <b>{stats['bearish_gaps']}</b>\n"
            f"🔄 Inversions: <b>{stats['reversals']}</b>\n"
            f"⏱️ Fréquence moyenne: {freq_text}\n"
            f"💡 Tendance actuelle: {trend_text}\n"
            f"\n"
            f"<b>💰 TRADING PERFORMANCE:</b>\n"
            f"{pnl_emoji} P&L cumulé: <b>{pnl:+.2f} USD</b>\n"
            f"📊 Nombre de trades: <b>{stats['total_trades']}</b>\n"
            f"✅ Trades gagnants: <b>{stats['winning_trades']}</b>\n"
            f"❌ Trades perdants: <b>{stats['losing_trades']}</b>\n"
            f"🎯 Win rate: <b>{stats['win_rate']:.1f}%</b>\n"
            f"💵 Volume cumulé: <b>${stats['cumulative_volume_usd']:,.0f}</b>\n"
            f"\n"
            f"<b>📉 AVERAGES:</b>\n"
            f"✅ Trade moyen gagnant: <b>+{stats['avg_winning_trade']:.2f} USD</b>\n"
            f"❌ Trade moyen perdant: <b>{stats['avg_losing_trade']:.2f} USD</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        await self._send_message(message)


# ════════════════════════════════════════════════════════════════════════════
# BINANCE API HELPERS
# ════════════════════════════════════════════════════════════════════════════


async def fetch_historical_klines(
    symbol: str, interval: str, limit: int = 100
) -> List[Candle]:
    """Fetch historical klines from Binance Futures REST API.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        interval: Kline interval (e.g., "5m", "15m")
        limit: Number of klines to fetch (default 100)

    Returns:
        List of Candle objects

    Raises:
        Exception if API request fails
    """
    url = f"{BINANCE_FUTURES_API}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch klines: {resp.status}")

            data = await resp.json()

            candles = []
            for kline in data:
                candle = Candle(
                    open_time_ms=int(kline[0]),
                    close_time_ms=int(kline[6]),
                    open=float(kline[1]),
                    high=float(kline[2]),
                    low=float(kline[3]),
                    close=float(kline[4]),
                )
                candles.append(candle)

            LOGGER.info(f"Fetched {len(candles)} historical candles for {symbol}")
            return candles


# ════════════════════════════════════════════════════════════════════════════
# MAIN WEBSOCKET LOOP
# ════════════════════════════════════════════════════════════════════════════


def parse_stats_interval(interval_str: str) -> int:
    """Parse stats interval string to minutes.

    Args:
        interval_str: Interval string (e.g., "10m", "30m", "1h", "2h")

    Returns:
        Interval in minutes
    """
    interval_str = interval_str.strip().lower()
    if interval_str.endswith("m"):
        return int(interval_str[:-1])
    elif interval_str.endswith("h"):
        return int(interval_str[:-1]) * 60
    elif interval_str.endswith("d"):
        return int(interval_str[:-1]) * 1440
    else:
        # Default to minutes if no suffix
        return int(interval_str)


async def listen_for_gaps(
    symbol: str,
    timeframe: str,
    gap_recorder: ExtGapRecorder,
    trade_recorder: TradeRecorder,
    trade_manager: ExtGapTradeManager,
    notifier: Optional[TelegramExtGapNotifier],
    stats_interval: str = "4h",
) -> None:
    """Main loop: connect to WebSocket, detect gaps and trade (no historical data).

    Args:
        symbol: Trading symbol
        timeframe: Kline interval
        gap_recorder: Gap CSV recorder
        trade_recorder: Trade CSV recorder
        trade_manager: Trade manager
        notifier: Telegram notifier (optional)
        stats_interval: Statistics notification interval (e.g., "10m", "30m", "1h")
    """
    # Initialize symbol state (no historical data - only detect new gaps going forward)
    symbol_state = ExternalGapSymbolState(symbol)

    # Initialize statistics tracking
    gap_stats = GapStatistics()

    # Parse stats interval and initialize UTC-aligned boundary tracking
    stats_interval_minutes = parse_stats_interval(stats_interval)
    now = datetime.now(timezone.utc)
    last_stats_boundary = get_current_stats_boundary(now, stats_interval_minutes)

    LOGGER.info(
        f"Starting external gap detection for {symbol} (no historical data - detecting new gaps only)"
    )
    LOGGER.info(f"Statistics interval: {stats_interval} ({stats_interval_minutes} minutes, UTC-aligned)")

    # Track current price for potential exit on shutdown
    current_prices: Dict[str, float] = {}

    # Connect to WebSocket
    stream_name = f"{symbol.lower()}@kline_{timeframe}"
    url = f"{BINANCE_FUTURES_STREAM}?streams={stream_name}"

    LOGGER.info(f"Connecting to Binance WebSocket: {stream_name}")

    reconnect_delay = 1.0
    max_reconnect_delay = 60.0

    while True:
        try:
            async with websockets.connect(url) as ws:
                LOGGER.info(f"Connected to Binance WebSocket for {symbol}")
                reconnect_delay = 1.0  # Reset delay on successful connection

                async for message in ws:
                    try:
                        data = json.loads(message)
                        await _handle_stream_message(
                            data,
                            symbol_state,
                            gap_recorder,
                            trade_recorder,
                            trade_manager,
                            notifier,
                            current_prices,
                            gap_stats,
                        )

                        # Check if stats should be sent (UTC-aligned)
                        now = datetime.now(timezone.utc)
                        current_boundary = get_current_stats_boundary(now, stats_interval_minutes)
                        if current_boundary > last_stats_boundary:
                            if notifier:
                                await notifier.notify_stats(symbol, stats_interval, gap_stats.to_dict())
                            last_stats_boundary = current_boundary
                            LOGGER.info(f"Sent periodic statistics ({stats_interval}) at UTC boundary {current_boundary.strftime('%H:%M')}")

                    except Exception as e:
                        LOGGER.error(f"Error processing message: {e}", exc_info=True)

        except (ConnectionClosedError, ConnectionClosedOK) as e:
            LOGGER.warning(f"WebSocket connection closed: {e}")
        except Exception as e:
            LOGGER.error(f"WebSocket error: {e}", exc_info=True)

        # Exponential backoff for reconnection
        LOGGER.info(f"Reconnecting in {reconnect_delay:.1f}s...")
        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)


async def _handle_stream_message(
    data: dict,
    symbol_state: ExternalGapSymbolState,
    gap_recorder: ExtGapRecorder,
    trade_recorder: TradeRecorder,
    trade_manager: ExtGapTradeManager,
    notifier: Optional[TelegramExtGapNotifier],
    current_prices: Dict[str, float],
    gap_stats: GapStatistics,
) -> None:
    """Handle incoming WebSocket message.

    Args:
        data: Parsed JSON data
        symbol_state: Symbol state tracker
        gap_recorder: Gap CSV recorder
        trade_recorder: Trade CSV recorder
        trade_manager: Trade manager
        notifier: Telegram notifier (optional)
        current_prices: Map of symbol -> current price
        gap_stats: Statistics tracker
    """
    # Extract kline data
    if "data" not in data:
        return

    stream_data = data["data"]

    if "k" not in stream_data:
        return

    kline = stream_data["k"]
    symbol = kline["s"]
    is_closed = kline["x"]

    # Update current price tracking
    current_price = float(kline["c"])
    current_prices[symbol] = current_price

    # Only process closed candles for gap detection
    if not is_closed:
        return

    # Create candle
    candle = Candle(
        open_time_ms=int(kline["t"]),
        close_time_ms=int(kline["T"]),
        open=float(kline["o"]),
        high=float(kline["h"]),
        low=float(kline["l"]),
        close=float(kline["c"]),
    )

    # Check for 24-hour expiry on existing position
    expiry_trade = trade_manager.check_24h_expiry(symbol, candle.close_time, candle.close)
    if expiry_trade is not None:
        trade_recorder.record(expiry_trade)
        gap_stats.record_trade_close(expiry_trade)
        if notifier:
            # For 24h expiry, there's no reversal - pass current polarity
            current_polarity = "bullish" if symbol_state.last_gap_polarity == "bullish" else "bearish"
            await notifier.notify_trade_close(
                expiry_trade,
                symbol_state.current_sequence_number,
                0,
                current_polarity,
                0.0,  # No new gap level for expiry
                symbol_state.last_gap_level or 0.0,
                0.0,  # No new entry price for expiry
            )

    # Detect new gap
    gap = symbol_state.add_candle(candle)

    if gap:
        # Record gap
        gap_recorder.record(gap)

        # Update statistics - use the is_reversal field from the gap detection
        gap_stats.record_gap(gap.polarity, gap.is_reversal, gap.sequence_number)

        # Notify gap detection (pass is_first_gap flag and sequence number)
        if notifier:
            await notifier.notify_gap_detection(gap, gap.is_first_gap, gap.sequence_number)

        if gap.is_first_gap:
            LOGGER.info(
                f"{symbol}: {gap.polarity.upper()} gap at {gap.gap_level:.2f} - first gap, waiting for reversal"
            )
        elif gap.is_reversal:
            # Execute trade IMMEDIATELY on reversal using candle close price
            side = "long" if gap.polarity == "bullish" else "short"
            entry_price = candle.close  # Use close price immediately

            LOGGER.info(
                f"{symbol}: {gap.polarity.upper()} reversal at {gap.gap_level:.2f} - executing {side.upper()} entry at {entry_price:.2f}"
            )

            # Open or reverse position
            closed_trade, new_trade = trade_manager.open_or_reverse(
                symbol, side, entry_price, candle.close_time
            )

            # Record and notify closed trade (reversal case)
            if closed_trade is not None:
                trade_recorder.record(closed_trade)
                gap_stats.record_trade_close(closed_trade)
                if notifier:
                    await notifier.notify_trade_close(
                        closed_trade,
                        gap.prev_sequence_number,  # Previous sequence from gap detection
                        gap.sequence_number,  # Current sequence
                        gap.polarity,  # New polarity
                        gap.gap_level,  # New gap level
                        gap.prev_gap_level,  # Previous gap level from gap detection
                        entry_price,  # New entry price
                    )

            # Notify new trade
            if notifier:
                await notifier.notify_trade_open(new_trade, gap.gap_level, gap.sequence_number)
        else:
            LOGGER.info(
                f"{symbol}: {gap.polarity.upper()} gap #{gap.sequence_number} at {gap.gap_level:.2f}"
            )


# ════════════════════════════════════════════════════════════════════════════
# PID FILE MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════


def check_pid_file(pid_file: Path) -> None:
    """Check if PID file exists and process is running. Exit if duplicate.

    Args:
        pid_file: Path to PID file
    """
    current_pid = os.getpid()

    if pid_file.exists():
        try:
            with open(pid_file) as f:
                old_pid = int(f.read().strip())

            # If PID file contains our own PID, it was written by the start script - this is OK
            if old_pid == current_pid:
                LOGGER.debug(f"PID file already contains current PID {current_pid} (written by start script)")
                return

            # Check if process is running (Unix-like systems)
            if sys.platform != "win32":
                import errno

                try:
                    os.kill(old_pid, 0)
                    LOGGER.error(
                        f"Another instance is already running (PID {old_pid}). Exiting."
                    )
                    sys.exit(1)
                except OSError as e:
                    if e.errno == errno.ESRCH:
                        # Process not running - stale PID file
                        LOGGER.warning(f"Stale PID file found, removing")
                        pid_file.unlink()
                    else:
                        raise
            else:
                # Windows: just log warning (no reliable way to check)
                LOGGER.warning(
                    f"PID file exists (PID {old_pid}) - if no other instance is running, delete it manually"
                )

        except (ValueError, FileNotFoundError):
            # Invalid or missing PID file
            LOGGER.warning("Invalid PID file found, removing")
            pid_file.unlink()

    # Write current PID (if not already written)
    if not pid_file.exists() or pid_file.read_text().strip() != str(current_pid):
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pid_file, "w") as f:
            f.write(str(current_pid))

    LOGGER.info(f"PID file created: {pid_file}")


def cleanup_pid_file(pid_file: Path) -> None:
    """Remove PID file.

    Args:
        pid_file: Path to PID file
    """
    if pid_file.exists():
        pid_file.unlink()
        LOGGER.info("PID file removed")


# ════════════════════════════════════════════════════════════════════════════
# CLI AND MAIN
# ════════════════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Binance Futures External Gap Indicator with simulated trading"
    )

    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading symbol (default: BTCUSDT)",
    )

    parser.add_argument(
        "--timeframe",
        type=str,
        default="1h",
        help="Kline interval (default: 1h)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="data/indicators/gaps/binance_extgap_1h_gaps.csv",
        help="Output CSV file for gaps (default: data/indicators/gaps/binance_extgap_1h_gaps.csv)",
    )

    parser.add_argument(
        "--trades-output",
        type=str,
        default="data/indicators/trades/binance_extgap_1h_trades.csv",
        help="Output CSV file for trades (default: data/indicators/trades/binance_extgap_1h_trades.csv)",
    )

    parser.add_argument(
        "--notional",
        type=float,
        default=DEFAULT_NOTIONAL,
        help=f"Position size in USD (default: {DEFAULT_NOTIONAL})",
    )

    parser.add_argument(
        "--entry-fee-rate",
        type=float,
        default=DEFAULT_ENTRY_FEE_RATE,
        help=f"Entry fee rate (default: {DEFAULT_ENTRY_FEE_RATE})",
    )

    parser.add_argument(
        "--exit-fee-rate",
        type=float,
        default=DEFAULT_EXIT_FEE_RATE,
        help=f"Exit fee rate (default: {DEFAULT_EXIT_FEE_RATE})",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--stats-interval",
        type=str,
        default=None,
        help="Statistics notification interval (e.g., 4h, 6h, 8h). Defaults to STATS_INTERVAL_EXTGAP_1H env var or 4h",
    )

    return parser.parse_args()


def setup_logging(log_level: str, timeframe: str) -> None:
    """Configure logging.

    Args:
        log_level: Log level string
        timeframe: Timeframe string (e.g., "1m", "5m", "15m", "1h")
    """
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)

    # Configure stdout handler with UTF-8 encoding for Windows emoji support
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setStream(open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace'))

    # Dynamic log file based on timeframe
    log_file = f"logs/indicators/extgap_indicator_{timeframe}.log"

    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            stdout_handler,
            logging.FileHandler(log_file, encoding='utf-8'),
        ],
    )

    # Suppress Telegram library DEBUG logs to avoid emoji encoding issues on Windows
    logging.getLogger("telegram").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def main() -> None:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.log_level, args.timeframe)

    # Determine stats interval: CLI arg > env var > default
    stats_interval = args.stats_interval
    if stats_interval is None:
        # Check for timeframe-specific environment variable
        tf_upper = args.timeframe.upper()
        stats_interval = os.getenv(f"STATS_INTERVAL_EXTGAP_{tf_upper}", "4h")

    LOGGER.info("=" * 80)
    LOGGER.info("Binance Futures External Gap Indicator")
    LOGGER.info("=" * 80)
    LOGGER.info(f"Symbol: {args.symbol}")
    LOGGER.info(f"Timeframe: {args.timeframe}")
    LOGGER.info(f"Stats interval: {stats_interval}")
    LOGGER.info(f"Notional: ${args.notional}")
    LOGGER.info(f"Entry fee rate: {args.entry_fee_rate * 100:.3f}%")
    LOGGER.info(f"Exit fee rate: {args.exit_fee_rate * 100:.3f}%")
    LOGGER.info("=" * 80)

    # Check PID file
    pid_file = Path(f"binance_extgap_indicator_{args.timeframe}.pid")
    check_pid_file(pid_file)

    # Initialize components
    gap_recorder = ExtGapRecorder(Path(args.output))
    trade_recorder = TradeRecorder(Path(args.trades_output))
    trade_manager = ExtGapTradeManager(
        args.notional, args.entry_fee_rate, args.exit_fee_rate
    )
    notifier = TelegramExtGapNotifier.from_env(args.timeframe)

    # Send start notification
    if notifier:
        await notifier.notify_status("started", symbol=args.symbol, stats_interval=stats_interval)

    try:
        # Run main loop
        await listen_for_gaps(
            args.symbol,
            args.timeframe,
            gap_recorder,
            trade_recorder,
            trade_manager,
            notifier,
            stats_interval,
        )

    except KeyboardInterrupt:
        LOGGER.info("Received shutdown signal")
        if notifier:
            await notifier.notify_status("stopped", "User interrupt")

    except Exception as e:
        LOGGER.error(f"Fatal error: {e}", exc_info=True)
        if notifier:
            await notifier.notify_status("stopped", f"Error: {e}")
        raise

    finally:
        cleanup_pid_file(pid_file)
        LOGGER.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
