#!/usr/bin/env python3
"""Heikin-Ashi Bands Breakout Indicator for Binance Futures.

This script implements the "[THE] HA Bands v5" indicator logic:
- Tracks HH Band (resistance) from bullish HA sequences
- Tracks LL Band (support) from bearish HA sequences
- Sends signals when regular price crosses above HH Band or below LL Band

Based on PineScript indicator by THE.

Usage:
    python Heinkin-ashin/binance_ha_bands_1m.py --symbol BTCUSDT --timeframe 1m
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import aiohttp
import websockets
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

# Load .env from config directory
env_path = Path(__file__).parent.parent / "config" / ".env"
load_dotenv(dotenv_path=env_path)

LOGGER = logging.getLogger("ha_bands_indicator")

BINANCE_FUTURES_STREAM = "wss://fstream.binance.com/stream"


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
class HABandsSignal:
    """Detected HA Bands breakout signal."""

    detected_at: datetime
    symbol: str
    signal_type: str  # "bullish_breakout" or "bearish_breakout"
    price: float  # Price that triggered the breakout
    hh_band: Optional[float]  # Current HH Band level
    ll_band: Optional[float]  # Current LL Band level


@dataclass
class HATunnelChange:
    """Represents a tunnel coordinate change event."""

    timestamp: datetime
    symbol: str
    timeframe: str  # e.g., "1m", "5m", "1h"
    direction: str  # "bullish_to_bearish" or "bearish_to_bullish"
    changed_band: str  # "hh" or "ll"
    hh_band: Optional[float]
    ll_band: Optional[float]


@dataclass
class HABandsStatistics:
    """Tracks statistics for HA Bands detection."""

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    bullish_breakouts: int = 0
    bearish_breakouts: int = 0
    total_signals: int = 0
    hh_band_updates: int = 0
    ll_band_updates: int = 0

    @property
    def uptime_minutes(self) -> float:
        """Calculate uptime in minutes."""
        return (datetime.now(timezone.utc) - self.start_time).total_seconds() / 60

    def record_signal(self, signal_type: str) -> None:
        """Record a signal."""
        self.total_signals += 1
        if signal_type == "bullish_breakout":
            self.bullish_breakouts += 1
        else:
            self.bearish_breakouts += 1

    def to_dict(self) -> dict:
        """Convert to dictionary for notification."""
        return {
            "uptime_minutes": self.uptime_minutes,
            "bullish_breakouts": self.bullish_breakouts,
            "bearish_breakouts": self.bearish_breakouts,
            "total_signals": self.total_signals,
            "hh_band_updates": self.hh_band_updates,
            "ll_band_updates": self.ll_band_updates,
        }


# ════════════════════════════════════════════════════════════════════════════
# HA BANDS STATE
# ════════════════════════════════════════════════════════════════════════════


class HABandsState:
    """Tracks Heikin-Ashi Bands for a single symbol.

    Based on "[THE] HA Bands v5" PineScript indicator:
    - HH Band: Highest high during bullish HA sequences, locked on reversal to bearish
    - LL Band: Lowest low during bearish HA sequences, locked on reversal to bullish
    - Signals when regular price crosses above HH or below LL band
    """

    def __init__(self, symbol: str, timeframe: str = "1m"):
        """Initialize HA Bands state.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            timeframe: Timeframe string (e.g., "1m", "5m", "1h")
        """
        self.symbol = symbol
        self.timeframe = timeframe

        # Heikin-Ashi state (for calculating HA candles)
        self.prev_ha_open: Optional[float] = None
        self.prev_ha_close: Optional[float] = None
        self.prev_ha_is_bullish: Optional[bool] = None

        # Sequence tracking (highest/lowest during current sequence)
        self.highest_group_high: Optional[float] = None
        self.lowest_group_low: Optional[float] = None

        # Locked bands (set on HA reversal)
        self.hh_band: Optional[float] = None  # Resistance - locked on bear reversal
        self.ll_band: Optional[float] = None  # Support - locked on bull reversal

        # Track if bands have been crossed (avoid duplicate signals)
        self.hh_crossed: bool = False
        self.ll_crossed: bool = False

        # Initialization flag
        self.is_initialized = False

    def add_candle(self, candle: Candle) -> Tuple[Optional[HABandsSignal], Optional[HATunnelChange]]:
        """Process new closed candle and check for breakouts.

        Args:
            candle: Closed candle to process

        Returns:
            Tuple of (HABandsSignal if breakout detected, HATunnelChange if tunnel updated)
        """
        # Calculate Heikin-Ashi values from regular candle
        ha_close = (candle.open + candle.high + candle.low + candle.close) / 4

        if self.prev_ha_open is None:
            # First candle - use simplified HA open
            ha_open = (candle.open + candle.close) / 2
        else:
            # Subsequent candles - use proper HA open formula
            ha_open = (self.prev_ha_open + self.prev_ha_close) / 2

        ha_high = max(candle.high, ha_open, ha_close)
        ha_low = min(candle.low, ha_open, ha_close)

        # Determine HA candle polarity
        ha_is_bullish = ha_close > ha_open
        ha_is_bearish = ha_close < ha_open

        # Detect reversals
        ha_bull_rev = (self.prev_ha_is_bullish is False) and ha_is_bullish  # bear→bull
        ha_bear_rev = (self.prev_ha_is_bullish is True) and ha_is_bearish   # bull→bear

        signal = None
        tunnel_change = None

        # Handle bullish HA candle
        if ha_is_bullish:
            # Lock LL band on bull reversal (bearish sequence just ended) - BEFORE resetting
            if ha_bull_rev and self.lowest_group_low is not None:
                old_ll = self.ll_band
                self.ll_band = self.lowest_group_low
                self.ll_crossed = False  # Reset crossed flag for new band
                LOGGER.info(f"{self.symbol}: LL Band locked at {self.ll_band:.2f} (was {old_ll})")

                # Create tunnel change notification
                tunnel_change = HATunnelChange(
                    timestamp=datetime.now(timezone.utc),
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    direction="bearish_to_bullish",
                    changed_band="ll",
                    hh_band=self.hh_band,
                    ll_band=self.ll_band,
                )

            if ha_bull_rev or self.highest_group_high is None:
                # Start new bullish sequence
                self.highest_group_high = ha_high
                self.lowest_group_low = None  # Reset bearish tracking
                LOGGER.debug(f"{self.symbol}: New bullish sequence started, tracking high: {ha_high:.2f}")
            else:
                # Continue bullish sequence - update highest high if new high
                if ha_high > self.highest_group_high:
                    self.highest_group_high = ha_high
                    LOGGER.debug(f"{self.symbol}: Updated highest group high: {ha_high:.2f}")

        # Handle bearish HA candle
        elif ha_is_bearish:
            # Lock HH band on bear reversal (bullish sequence just ended) - BEFORE resetting
            if ha_bear_rev and self.highest_group_high is not None:
                old_hh = self.hh_band
                self.hh_band = self.highest_group_high
                self.hh_crossed = False  # Reset crossed flag for new band
                LOGGER.info(f"{self.symbol}: HH Band locked at {self.hh_band:.2f} (was {old_hh})")

                # Create tunnel change notification
                tunnel_change = HATunnelChange(
                    timestamp=datetime.now(timezone.utc),
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    direction="bullish_to_bearish",
                    changed_band="hh",
                    hh_band=self.hh_band,
                    ll_band=self.ll_band,
                )

            if ha_bear_rev or self.lowest_group_low is None:
                # Start new bearish sequence
                self.lowest_group_low = ha_low
                self.highest_group_high = None  # Reset bullish tracking
                LOGGER.debug(f"{self.symbol}: New bearish sequence started, tracking low: {ha_low:.2f}")
            else:
                # Continue bearish sequence - update lowest low if new low
                if ha_low < self.lowest_group_low:
                    self.lowest_group_low = ha_low
                    LOGGER.debug(f"{self.symbol}: Updated lowest group low: {ha_low:.2f}")

        # Check for breakout signals (using REGULAR price CLOSE, not just high/low)
        # Bullish breakout: candle CLOSES above HH band
        if self.hh_band is not None and not self.hh_crossed:
            if candle.close > self.hh_band:
                signal = HABandsSignal(
                    detected_at=datetime.now(timezone.utc),
                    symbol=self.symbol,
                    signal_type="bullish_breakout",
                    price=candle.close,
                    hh_band=self.hh_band,
                    ll_band=self.ll_band,
                )
                self.hh_crossed = True
                LOGGER.info(
                    f"{self.symbol}: BULLISH BREAKOUT! Close {candle.close:.2f} > HH Band {self.hh_band:.2f}"
                )

        # Bearish breakout: candle CLOSES below LL band
        if self.ll_band is not None and not self.ll_crossed:
            if candle.close < self.ll_band:
                signal = HABandsSignal(
                    detected_at=datetime.now(timezone.utc),
                    symbol=self.symbol,
                    signal_type="bearish_breakout",
                    price=candle.close,
                    hh_band=self.hh_band,
                    ll_band=self.ll_band,
                )
                self.ll_crossed = True
                LOGGER.info(
                    f"{self.symbol}: BEARISH BREAKOUT! Close {candle.close:.2f} < LL Band {self.ll_band:.2f}"
                )

        # Update state for next candle
        self.prev_ha_open = ha_open
        self.prev_ha_close = ha_close
        self.prev_ha_is_bullish = ha_is_bullish
        self.is_initialized = True

        return signal, tunnel_change


# ════════════════════════════════════════════════════════════════════════════
# CSV RECORDER
# ════════════════════════════════════════════════════════════════════════════


class HABandsRecorder:
    """Records HA Bands signals to CSV."""

    def __init__(self, output_path: Path):
        """Initialize signal recorder.

        Args:
            output_path: Path to output CSV file
        """
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write header if file doesn't exist
        if not self.output_path.exists():
            with open(self.output_path, "w") as f:
                f.write("detected_at_utc,symbol,signal_type,price,hh_band,ll_band\n")

    def record(self, signal: HABandsSignal) -> None:
        """Record signal to CSV.

        Args:
            signal: Signal to record
        """
        with open(self.output_path, "a") as f:
            hh_str = f"{signal.hh_band:.8f}" if signal.hh_band is not None else "N/A"
            ll_str = f"{signal.ll_band:.8f}" if signal.ll_band is not None else "N/A"
            f.write(
                f"{signal.detected_at.isoformat()},"
                f"{signal.symbol},"
                f"{signal.signal_type},"
                f"{signal.price:.8f},"
                f"{hh_str},"
                f"{ll_str}\n"
            )
        LOGGER.debug(f"Recorded {signal.signal_type} signal for {signal.symbol}")


# ════════════════════════════════════════════════════════════════════════════
# TELEGRAM NOTIFICATIONS
# ════════════════════════════════════════════════════════════════════════════


class TelegramHABandsNotifier:
    """Sends Telegram notifications for HA Bands breakouts using aiohttp."""

    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str, chat_ids: List[str], instance_id: str, timeframe: str):
        """Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot API token
            chat_ids: List of chat IDs to send notifications to
            instance_id: Instance identifier (e.g., "LOCAL", "AWS")
            timeframe: Timeframe string (e.g., "1m", "5m")
        """
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.instance_id = instance_id
        self.timeframe = timeframe
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    @classmethod
    def from_env(cls, timeframe: str) -> Optional["TelegramHABandsNotifier"]:
        """Create notifier from environment variables.

        Checks for timeframe-specific variables first, falls back to generic.
        - TELEGRAM_BOT_TOKEN_HABANDS_{TIMEFRAME} or TELEGRAM_BOT_TOKEN
        - TELEGRAM_CHAT_IDS_HABANDS_{TIMEFRAME} or TELEGRAM_CHAT_IDS

        Args:
            timeframe: Timeframe string (e.g., "1m", "5m")

        Returns:
            TelegramHABandsNotifier instance or None if credentials missing
        """
        tf_upper = timeframe.upper()
        bot_token = (
            os.getenv(f"TELEGRAM_BOT_TOKEN_HABANDS_{tf_upper}")
            or os.getenv("TELEGRAM_BOT_TOKEN")
        )
        chat_ids_str = (
            os.getenv(f"TELEGRAM_CHAT_IDS_HABANDS_{tf_upper}")
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
        """Send message to all configured chat IDs using aiohttp.

        Args:
            message: Message text to send
        """
        session = await self._get_session()
        url = self.TELEGRAM_API_URL.format(token=self.bot_token)

        for chat_id in self.chat_ids:
            try:
                payload = {
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                }
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        LOGGER.error(f"Failed to send Telegram message to {chat_id}: {error_text}")
                    else:
                        LOGGER.debug(f"Telegram message sent to {chat_id}")
            except Exception as e:
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
                f"🚀 <b>HA BANDS BOT DEMARRÉ - {symbol}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {current_time} UTC\n"
                f"📊 Version: <b>HA Bands v1.0</b>\n"
                f"🖥️ Instance: <b>{self.instance_id}</b>\n"
                f"⏱️ Timeframe: <b>{self.timeframe}</b>\n"
                f"🔍 Statut: <b>Surveillance active</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Détection des breakouts HA Bands en cours..."
            )
        else:
            current_time = datetime.now(timezone.utc).strftime("%H:%M:%S")
            message = (
                f"🛑 <b>HA BANDS BOT ARRÊTÉ</b>\n"
                f"Instance: {self.instance_id}"
            )
            if reason:
                message += f"\nRaison: {reason}"

        await self._send_message(message)

    async def notify_breakout(self, signal: HABandsSignal) -> None:
        """Send breakout notification.

        Args:
            signal: Detected breakout signal
        """
        if signal.signal_type == "bullish_breakout":
            emoji = "🟢"
            direction = "BULLISH BREAKOUT"
            band_text = f"📈 HH Band: {signal.hh_band:,.2f} (CASSÉ)"
        else:
            emoji = "🔴"
            direction = "BEARISH BREAKOUT"
            band_text = f"📉 LL Band: {signal.ll_band:,.2f} (CASSÉ)"

        message = (
            f"🔔 <b>HA BANDS BREAKOUT - {signal.symbol}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {signal.detected_at.strftime('%H:%M:%S')} UTC | {self.timeframe}\n"
            f"{emoji} <b>{direction}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Prix: <b>{signal.price:,.2f}</b>\n"
            f"{band_text}\n"
        )

        # Add both bands info if available
        if signal.signal_type == "bullish_breakout" and signal.ll_band:
            message += f"📉 LL Band: {signal.ll_band:,.2f}\n"
        elif signal.signal_type == "bearish_breakout" and signal.hh_band:
            message += f"📈 HH Band: {signal.hh_band:,.2f}\n"

        message += f"━━━━━━━━━━━━━━━━━━━━"

        await self._send_message(message)

    async def notify_stats(self, symbol: str, stats: dict) -> None:
        """Send periodic statistics notification.

        Args:
            symbol: Trading symbol
            stats: Statistics dictionary
        """
        uptime_min = stats['uptime_minutes']
        if uptime_min < 60:
            uptime_text = f"{uptime_min:.0f}m"
        elif uptime_min < 1440:
            uptime_text = f"{uptime_min/60:.1f}h"
        else:
            uptime_text = f"{uptime_min/1440:.1f}d"

        message = (
            f"📊 <b>STATISTIQUES HA BANDS - {symbol}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {datetime.now(timezone.utc).strftime('%H:%M')} UTC\n"
            f"⏱️ Timeframe: <b>{self.timeframe}</b>\n"
            f"⏳ Uptime: <b>{uptime_text}</b>\n"
            f"\n"
            f"<b>📈 SIGNALS:</b>\n"
            f"🟢 Bullish breakouts: <b>{stats['bullish_breakouts']}</b>\n"
            f"🔴 Bearish breakouts: <b>{stats['bearish_breakouts']}</b>\n"
            f"📊 Total signals: <b>{stats['total_signals']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        await self._send_message(message)

    async def notify_tunnel_change(self, change: HATunnelChange) -> None:
        """Send notification when tunnel coordinates change.

        Args:
            change: Tunnel change event
        """
        direction_text = "Bearish → Bullish" if change.direction == "bearish_to_bullish" else "Bullish → Bearish"

        # Format which band changed
        if change.changed_band == "ll":
            changed_text = f"🔵 LL (Support): <b>{change.ll_band:,.4f}</b> ← NEW"
            other_text = f"⚪ HH (Resistance): {change.hh_band:,.4f}" if change.hh_band else "⚪ HH (Resistance): Not set"
        else:
            changed_text = f"🔴 HH (Resistance): <b>{change.hh_band:,.4f}</b> ← NEW"
            other_text = f"⚪ LL (Support): {change.ll_band:,.4f}" if change.ll_band else "⚪ LL (Support): Not set"

        message = (
            f"<b>🔄 HA Tunnel Update</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Symbol:</b> {change.symbol}\n"
            f"<b>Timeframe:</b> {change.timeframe}\n"
            f"<b>Polarity Reversal:</b> {direction_text}\n"
            f"\n"
            f"<b>Tunnel Coordinates:</b>\n"
            f"{changed_text}\n"
            f"{other_text}\n"
            f"\n"
            f"<i>{change.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
        )

        await self._send_message(message)


# ════════════════════════════════════════════════════════════════════════════
# MAIN WEBSOCKET LOOP
# ════════════════════════════════════════════════════════════════════════════


async def listen_for_signals(
    symbol: str,
    timeframe: str,
    recorder: HABandsRecorder,
    notifier: Optional[TelegramHABandsNotifier],
    stats_interval_minutes: int = 30,
) -> None:
    """Main loop: connect to WebSocket and detect HA Bands breakouts.

    Args:
        symbol: Trading symbol
        timeframe: Kline interval
        recorder: Signal CSV recorder
        notifier: Telegram notifier (optional)
        stats_interval_minutes: Statistics notification interval in minutes
    """
    # Initialize symbol state
    symbol_state = HABandsState(symbol, timeframe)

    # Initialize statistics tracking
    stats = HABandsStatistics()
    last_stats_time = datetime.now(timezone.utc)

    LOGGER.info(f"Starting HA Bands detection for {symbol} on {timeframe}")
    LOGGER.info(f"Statistics interval: {stats_interval_minutes} minutes")

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
                            recorder,
                            notifier,
                            stats,
                        )

                        # Check if stats should be sent
                        now = datetime.now(timezone.utc)
                        if (now - last_stats_time).total_seconds() >= stats_interval_minutes * 60:
                            if notifier:
                                await notifier.notify_stats(symbol, stats.to_dict())
                            last_stats_time = now
                            LOGGER.info(f"Sent periodic statistics ({stats_interval_minutes}m)")

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
    symbol_state: HABandsState,
    recorder: HABandsRecorder,
    notifier: Optional[TelegramHABandsNotifier],
    stats: HABandsStatistics,
) -> None:
    """Handle incoming WebSocket message.

    Args:
        data: Parsed JSON data
        symbol_state: Symbol state tracker
        recorder: Signal CSV recorder
        notifier: Telegram notifier (optional)
        stats: Statistics tracker
    """
    # Extract kline data
    if "data" not in data:
        return

    stream_data = data["data"]

    if "k" not in stream_data:
        return

    kline = stream_data["k"]
    is_closed = kline["x"]

    # Only process closed candles
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

    # Process candle and check for breakout
    signal, tunnel_change = symbol_state.add_candle(candle)

    # Send tunnel change notification if coordinates updated
    if tunnel_change and notifier:
        await notifier.notify_tunnel_change(tunnel_change)
        LOGGER.info(
            f"{tunnel_change.symbol}: Tunnel updated - {tunnel_change.direction}, "
            f"changed {tunnel_change.changed_band.upper()} band"
        )

    if signal:
        # Record signal
        recorder.record(signal)

        # Update statistics
        stats.record_signal(signal.signal_type)

        # Send notification
        if notifier:
            await notifier.notify_breakout(signal)

        LOGGER.info(
            f"{signal.symbol}: {signal.signal_type.upper()} at {signal.price:.2f}"
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

            if old_pid == current_pid:
                LOGGER.debug(f"PID file already contains current PID {current_pid}")
                return

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
                        LOGGER.warning("Stale PID file found, removing")
                        pid_file.unlink()
                    else:
                        raise
            else:
                LOGGER.warning(
                    f"PID file exists (PID {old_pid}) - delete manually if no other instance is running"
                )

        except (ValueError, FileNotFoundError):
            LOGGER.warning("Invalid PID file found, removing")
            pid_file.unlink()

    # Write current PID
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
        description="Heikin-Ashi Bands Breakout Indicator for Binance Futures"
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
        default="1m",
        help="Kline interval (default: 1m)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="Heinkin-ashin/data/signals/ha_bands_1m_signals.csv",
        help="Output CSV file for signals",
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
        type=int,
        default=30,
        help="Statistics notification interval in minutes (default: 30)",
    )

    return parser.parse_args()


def setup_logging(log_level: str, timeframe: str) -> None:
    """Configure logging.

    Args:
        log_level: Log level string
        timeframe: Timeframe string
    """
    # Use UTC for all log timestamps
    logging.Formatter.converter = time.gmtime

    # Ensure logs directory exists
    log_dir = Path("Heinkin-ashin/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure stdout handler with UTF-8 encoding
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setStream(
        open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')
    )

    log_file = log_dir / f"ha_bands_{timeframe}.log"

    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            stdout_handler,
            logging.FileHandler(log_file, encoding='utf-8'),
        ],
    )

    # Suppress verbose library logs
    logging.getLogger("telegram").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def main() -> None:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.log_level, args.timeframe)

    LOGGER.info("=" * 80)
    LOGGER.info("Heikin-Ashi Bands Breakout Indicator")
    LOGGER.info("=" * 80)
    LOGGER.info(f"Symbol: {args.symbol}")
    LOGGER.info(f"Timeframe: {args.timeframe}")
    LOGGER.info(f"Stats interval: {args.stats_interval} minutes")
    LOGGER.info("=" * 80)

    # Check PID file
    pid_file = Path(f"Heinkin-ashin/ha_bands_{args.timeframe}.pid")
    check_pid_file(pid_file)

    # Initialize components
    recorder = HABandsRecorder(Path(args.output))
    notifier = TelegramHABandsNotifier.from_env(args.timeframe)

    # Send start notification
    if notifier:
        await notifier.notify_status("started", symbol=args.symbol)

    try:
        # Run main loop
        await listen_for_signals(
            args.symbol,
            args.timeframe,
            recorder,
            notifier,
            args.stats_interval,
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
