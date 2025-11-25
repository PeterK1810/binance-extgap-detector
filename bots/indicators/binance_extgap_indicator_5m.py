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
    python paradex_extgap/binance_extgap_indicator_5m.py --symbol BTCUSDT --timeframe 2m
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
from datetime import datetime, timezone
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
    sequence_number: int = 1  # Sequence number within current trend


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


# ════════════════════════════════════════════════════════════════════════════
# EXTERNAL GAP SYMBOL STATE
# ════════════════════════════════════════════════════════════════════════════


class ExternalGapSymbolState:
    """Tracks external gaps for a single symbol using candidate tracking.

    External gaps are detected when price breaks beyond candidate extremes:
    - Bullish gap: Current low > bullish_candidate_high (lowest high since last gap)
    - Bearish gap: Current high < bearish_candidate_low (highest low since last gap)

    This is more general than 3-candle FVG and detects gaps sooner.
    """

    def __init__(self, symbol: str):
        """Initialize symbol state.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
        """
        self.symbol = symbol
        self.candle_history: Deque[Candle] = deque(maxlen=500)

        # Gap tracking
        self.last_gap_level: Optional[float] = None
        self.last_gap_polarity: Optional[str] = None  # "bullish" or "bearish"
        self.last_gap_bar_idx: Optional[int] = None

        # Candidate tracking (bars after last gap)
        self.group_bars: List[Candle] = []  # Bars since last gap
        self.bearish_candidate_low: Optional[float] = None  # Highest low
        self.bearish_candidate_bar: Optional[Candle] = None
        self.bullish_candidate_high: Optional[float] = None  # Lowest high
        self.bullish_candidate_bar: Optional[Candle] = None

        # Pending entry (set when reversal detected, executed on next candle open)
        self.pending_entry_side: Optional[str] = None  # "long" or "short"
        self.pending_entry_gap_level: Optional[float] = None

        # First gap tracking (for first-reversal entry strategy)
        self.first_gap_detected = False
        self.first_gap_polarity: Optional[str] = None  # Track first gap polarity

        # Sequence tracking
        self.current_sequence_number: int = 0
        self.last_sequence_number: int = 0  # Previous sequence before reversal

        # Initialization flag
        self.is_initialized = False

    def add_candle(self, candle: Candle) -> Optional[ExternalGapDetection]:
        """Process new closed candle and detect external gaps.

        Args:
            candle: Closed candle to process

        Returns:
            ExternalGapDetection if gap detected, None otherwise
        """
        self.candle_history.append(candle)

        # First-time initialization (need at least 1 candle to start)
        if not self.is_initialized:
            self.bearish_candidate_low = candle.low
            self.bearish_candidate_bar = candle
            self.bullish_candidate_high = candle.high
            self.bullish_candidate_bar = candle
            self.group_bars.append(candle)
            self.is_initialized = True
            return None

        # Check for new gap
        gap_detected = False
        is_bearish = False
        gap_level = 0.0
        gap_bar: Optional[Candle] = None

        if (
            self.bearish_candidate_low is not None
            and candle.high < self.bearish_candidate_low
        ):
            # Bearish gap: current high < candidate low (highest low)
            gap_detected = True
            is_bearish = True
            gap_level = self.bearish_candidate_low
            gap_bar = self.bearish_candidate_bar

        elif (
            self.bullish_candidate_high is not None
            and candle.low > self.bullish_candidate_high
        ):
            # Bullish gap: current low > candidate high (lowest high)
            gap_detected = True
            is_bearish = False
            gap_level = self.bullish_candidate_high
            gap_bar = self.bullish_candidate_bar

        if gap_detected and gap_bar is not None:
            current_polarity = "bearish" if is_bearish else "bullish"

            # Check if this is first gap or a reversal
            is_reversal = False
            is_first_gap = False

            if not self.first_gap_detected:
                # First gap detected - record it but don't trade
                self.first_gap_detected = True
                self.first_gap_polarity = current_polarity
                is_first_gap = True
                LOGGER.info(
                    f"{self.symbol}: First {current_polarity} gap detected at {gap_level:.2f} - waiting for reversal to start trading"
                )
            elif self.first_gap_polarity != current_polarity:
                # This is a reversal - allow trading
                is_reversal = True
                LOGGER.info(
                    f"{self.symbol}: {current_polarity.upper()} reversal gap detected at {gap_level:.2f} - preparing entry"
                )
            else:
                # Same polarity as first gap - still waiting for reversal
                LOGGER.info(
                    f"{self.symbol}: {current_polarity.upper()} gap detected at {gap_level:.2f} - still waiting for reversal"
                )

            # Update sequence tracking
            if is_first_gap:
                # First gap detected - initialize sequence
                self.current_sequence_number = 1
            elif self.last_gap_polarity is not None and self.last_gap_polarity != current_polarity:
                # Reversal: save previous sequence and reset to 1
                self.last_sequence_number = self.current_sequence_number
                self.current_sequence_number = 1
            else:
                # Same polarity - increment sequence
                self.current_sequence_number += 1

            # Create gap detection with is_first_gap flag and sequence number
            detection = ExternalGapDetection(
                detected_at=datetime.now(timezone.utc),
                symbol=self.symbol,
                polarity=current_polarity,
                gap_level=gap_level,
                gap_opening_bar_time=gap_bar.close_time,
                detection_bar_time=candle.close_time,
                is_first_gap=is_first_gap,
                sequence_number=self.current_sequence_number,
            )

            # Update gap tracking
            self.last_gap_level = gap_level
            self.last_gap_polarity = current_polarity
            self.last_gap_bar_idx = len(self.candle_history) - 1

            # Clean up group: start fresh with current bar
            self.group_bars = [candle]

            # Reset candidates to current bar
            self.bearish_candidate_low = candle.low
            self.bearish_candidate_bar = candle
            self.bullish_candidate_high = candle.high
            self.bullish_candidate_bar = candle

            # Set pending entry only if reversal detected (not first gap)
            if is_reversal:
                self.pending_entry_side = "long" if not is_bearish else "short"
                self.pending_entry_gap_level = gap_level

            return detection

        else:
            # No gap - update candidates and group
            self.group_bars.append(candle)

            # Update bearish candidate (highest low)
            if (
                self.bearish_candidate_low is None
                or candle.low > self.bearish_candidate_low
            ):
                self.bearish_candidate_low = candle.low
                self.bearish_candidate_bar = candle

            # Update bullish candidate (lowest high)
            if (
                self.bullish_candidate_high is None
                or candle.high < self.bullish_candidate_high
            ):
                self.bullish_candidate_high = candle.high
                self.bullish_candidate_bar = candle

            return None

    def get_pending_entry(self, next_open: float) -> Optional[Tuple[str, float, float]]:
        """Get pending entry and clear it.

        Args:
            next_open: Open price of next candle

        Returns:
            Tuple of (side, entry_price, gap_level) if pending entry exists, None otherwise
        """
        if self.pending_entry_side is not None:
            side = self.pending_entry_side
            gap_level = self.pending_entry_gap_level
            self.pending_entry_side = None
            self.pending_entry_gap_level = None
            return (side, next_open, gap_level)
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
        # Use 3M credentials for 3M timeframe
        bot_token = (
            os.getenv("TELEGRAM_BOT_TOKEN_EXTGAP_5M")
            or os.getenv("TELEGRAM_BOT_TOKEN")
        )
        chat_ids_str = (
            os.getenv("TELEGRAM_CHAT_IDS_EXTGAP_5M")
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

    async def notify_status(self, status: str, reason: str = "", symbol: str = "BTCUSDT") -> None:
        """Send status notification (start/stop).

        Args:
            status: "started" or "stopped"
            reason: Optional reason for status change
            symbol: Trading symbol
        """
        if status == "started":
            current_time = datetime.now(timezone.utc).strftime("%H:%M:%S")
            message = (
                f"🚀 <b>BOT INDICATOR {self.timeframe.upper()} DÉMARRÉ - {symbol}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {current_time} UTC\n"
                f"📊 Version: <b>External Gap Indicator</b>\n"
                f"🖥️ Instance: <b>{self.instance_id}</b>\n"
                f"⏱️ Timeframe: <b>{self.timeframe}</b>\n"
                f"💰 Notional: <b>$1000</b>\n"
                f"🔍 Statut: <b>Surveillance active</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Détection des gaps externes et trading en cours...\n"
                f"📈 Stratégie: Trend-following avec position reversal\n"
                f"🎯 Entry: Open du candle suivant détection\n"
                f"⏳ Exit: Gap opposé ou auto-close 24h"
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
            message = (
                f"📊 <b>GAP {gap.polarity.upper()} #{sequence_number} DÉTECTÉ - {gap.symbol}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {gap.detection_bar_time.strftime('%H:%M:%S')} UTC\n"
                f"💰 Niveau: <b>{gap.gap_level:,.2f} USDT</b>\n"
                f"📈 Séquence: <b>{gap.polarity.upper()} #{sequence_number}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏳ Entrée pending sur prochain candle open"
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
            f"💸 Frais entrée: ${trade.entry_fee:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Sortie: Reversal sur gap opposé"
        )
        await self._send_message(message)

    async def notify_trade_close(self, result: TradeResult, prev_sequence: int = 0, new_sequence: int = 1, new_polarity: str = "unknown") -> None:
        """Send trade close notification.

        Args:
            result: Trade result
            prev_sequence: Previous sequence number
            new_sequence: New sequence number after reversal
            new_polarity: New polarity after reversal
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
            f"\n"
            f"💰 <b>P&L Position Fermée:</b>\n"
            f"  {status_emoji} {result.side}: <b>{pnl_sign}{result.realized_pnl:.2f} USD ({pnl_sign}{pnl_pct:.2f}%)</b>\n"
            f"  📊 Entrée: {result.entry_price:,.2f} → Sortie: {result.exit_price:,.2f}\n"
            f"  🔢 Quantité: {qty_btc:.6f} BTC\n"
            f"  💸 Frais totaux: ${result.total_fees:.2f}\n"
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 P&L cumulé: <b>{'+' if result.cumulative_pnl >= 0 else ''}{result.cumulative_pnl:.2f} USD</b>\n"
            f"📊 W/L: {result.cumulative_wins}/{result.cumulative_losses}\n"
            f"💸 Frais cumulés: ${result.cumulative_fees:.2f}"
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


async def listen_for_gaps(
    symbol: str,
    timeframe: str,
    gap_recorder: ExtGapRecorder,
    trade_recorder: TradeRecorder,
    trade_manager: ExtGapTradeManager,
    notifier: Optional[TelegramExtGapNotifier],
) -> None:
    """Main loop: connect to WebSocket, detect gaps and trade (no historical data).

    Args:
        symbol: Trading symbol
        timeframe: Kline interval
        gap_recorder: Gap CSV recorder
        trade_recorder: Trade CSV recorder
        trade_manager: Trade manager
        notifier: Telegram notifier (optional)
    """
    # Initialize symbol state (no historical data - only detect new gaps going forward)
    symbol_state = ExternalGapSymbolState(symbol)

    LOGGER.info(
        f"Starting external gap detection for {symbol} (no historical data - detecting new gaps only)"
    )

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
                        )
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
        if notifier:
            # For 24h expiry, there's no reversal - pass current polarity
            current_polarity = "bullish" if symbol_state.last_gap_polarity == "bullish" else "bearish"
            await notifier.notify_trade_close(expiry_trade, symbol_state.current_sequence_number, 0, current_polarity)

    # Check for pending entry from previous candle
    pending_entry = symbol_state.get_pending_entry(candle.open)
    if pending_entry is not None:
        side, entry_price, gap_level = pending_entry
        LOGGER.info(
            f"{symbol}: Executing pending {side.upper()} entry at {entry_price:.2f}"
        )

        # Open or reverse position
        closed_trade, new_trade = trade_manager.open_or_reverse(
            symbol, side, entry_price, candle.open_time
        )

        # Record and notify closed trade (reversal case - get gap polarity from new trade side)
        if closed_trade is not None:
            trade_recorder.record(closed_trade)
            if notifier:
                # New polarity is opposite of closed trade: if closed SHORT, new is bullish (LONG)
                new_polarity = "bullish" if new_trade.side == "long" else "bearish"
                await notifier.notify_trade_close(closed_trade, symbol_state.last_sequence_number, symbol_state.current_sequence_number, new_polarity)

        # Notify new trade (use gap_level from pending entry and current sequence number)
        if notifier and gap_level is not None:
            await notifier.notify_trade_open(new_trade, gap_level, symbol_state.current_sequence_number)

    # Detect new gap
    gap = symbol_state.add_candle(candle)

    if gap:
        # Record gap
        gap_recorder.record(gap)

        # Notify gap detection (pass is_first_gap flag and sequence number)
        if notifier:
            await notifier.notify_gap_detection(gap, gap.is_first_gap, gap.sequence_number)

        if gap.is_first_gap:
            LOGGER.info(
                f"{symbol}: {gap.polarity.upper()} gap at {gap.gap_level:.2f} - first gap, waiting for reversal"
            )
        else:
            LOGGER.info(
                f"{symbol}: {gap.polarity.upper()} gap at {gap.gap_level:.2f} - pending entry on next candle"
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
        default="5m",
        help="Kline interval (default: 5m)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="data/indicators/gaps/binance_extgap_5m_gaps.csv",
        help="Output CSV file for gaps (default: data/indicators/gaps/binance_extgap_5m_gaps.csv)",
    )

    parser.add_argument(
        "--trades-output",
        type=str,
        default="data/indicators/trades/binance_extgap_5m_trades.csv",
        help="Output CSV file for trades (default: data/indicators/trades/binance_extgap_5m_trades.csv)",
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

    LOGGER.info("=" * 80)
    LOGGER.info("Binance Futures External Gap Indicator")
    LOGGER.info("=" * 80)
    LOGGER.info(f"Symbol: {args.symbol}")
    LOGGER.info(f"Timeframe: {args.timeframe}")
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
        await notifier.notify_status("started")

    try:
        # Run main loop
        await listen_for_gaps(
            args.symbol,
            args.timeframe,
            gap_recorder,
            trade_recorder,
            trade_manager,
            notifier,
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
