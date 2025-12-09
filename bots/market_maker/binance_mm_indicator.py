#!/usr/bin/env python3
"""Binance Futures Market Maker with External Gap Signal Bias.

This script combines External Gap detection with market maker execution:
- Gap signals provide directional bias
- ATR-based grid of limit orders in biased direction
- Bullish gap -> BID (buy) orders only
- Bearish gap -> ASK (sell) orders only
- VWAP position aggregation from multiple fills
- Simulated fills based on candle OHLC

Usage:
    python bots/market_maker/binance_mm_indicator.py --symbol BTCUSDT --timeframe 5m
    python bots/market_maker/binance_mm_indicator.py --symbol ETHUSDT --timeframe 15m --grid-levels 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import websockets
from dotenv import load_dotenv
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bots.indicators.binance_extgap_indicator_5m import (
    Candle,
    ExternalGapSymbolState,
)
from bots.market_maker.models import GridConfig
from bots.market_maker.mm_execution_layer import MarketMakerExecutionLayer

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger("binance_mm_indicator")

# Binance endpoints
BINANCE_FUTURES_STREAM = "wss://fstream.binance.com/stream"


class BinanceMMIndicator:
    """Binance Futures Market Maker with Gap Signal Bias.

    Connects to Binance WebSocket, detects gaps, and executes
    market maker strategy with directional bias.
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        config: GridConfig,
        data_dir: Path,
    ):
        """Initialize the MM indicator.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            timeframe: Candle timeframe (e.g., "5m", "15m")
            config: Grid configuration
            data_dir: Directory for data output
        """
        self.symbol = symbol.upper()
        self.timeframe = timeframe
        self.config = config
        self.data_dir = data_dir

        # Create data directory
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize gap detector
        self.symbol_state = ExternalGapSymbolState(self.symbol)

        # Initialize MM execution layer
        self.mm_layer = MarketMakerExecutionLayer(
            symbol_state=self.symbol_state,
            config=config,
            data_dir=self.data_dir,
            timeframe=timeframe
        )

        # WebSocket state
        self.ws: Optional[WebSocketClientProtocol] = None
        self.running = False
        self.candle_count = 0

        LOGGER.info(
            f"Initialized MM indicator for {self.symbol} {self.timeframe}"
        )

    async def start(self) -> None:
        """Start the WebSocket connection and processing loop."""
        self.running = True

        # Build stream URL
        stream_name = f"{self.symbol.lower()}@kline_{self.timeframe}"
        url = f"{BINANCE_FUTURES_STREAM}?streams={stream_name}"

        LOGGER.info(f"Connecting to {url}")

        reconnect_delay = 1
        max_delay = 60

        while self.running:
            try:
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self.ws = ws
                    reconnect_delay = 1  # Reset on successful connect

                    LOGGER.info(f"Connected to Binance stream: {stream_name}")

                    await self._process_stream()

            except ConnectionClosedError as e:
                LOGGER.warning(f"Connection closed: {e}, reconnecting in {reconnect_delay}s")
            except ConnectionClosedOK:
                LOGGER.info("Connection closed normally")
                break
            except Exception as e:
                LOGGER.error(f"WebSocket error: {e}, reconnecting in {reconnect_delay}s")

            if self.running:
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_delay)

    async def _process_stream(self) -> None:
        """Process incoming WebSocket messages."""
        async for message in self.ws:
            if not self.running:
                break

            try:
                data = json.loads(message)
                await self._handle_message(data)
            except json.JSONDecodeError as e:
                LOGGER.error(f"JSON decode error: {e}")
            except Exception as e:
                LOGGER.exception(f"Error processing message: {e}")

    async def _handle_message(self, data: dict) -> None:
        """Handle a WebSocket message.

        Args:
            data: Parsed JSON message
        """
        # Extract kline data
        if "data" not in data:
            return

        kline_data = data["data"]
        if kline_data.get("e") != "kline":
            return

        kline = kline_data["k"]

        # Only process closed candles
        if not kline.get("x", False):
            return

        # Create Candle object
        candle = Candle(
            open_time_ms=kline["t"],
            close_time_ms=kline["T"],
            open=float(kline["o"]),
            high=float(kline["h"]),
            low=float(kline["l"]),
            close=float(kline["c"]),
        )

        self.candle_count += 1

        # Check 24h expiry before processing
        self.mm_layer.check_24h_expiry(candle)

        # Process candle through MM layer
        gap = self.mm_layer.process_candle(candle)

        # Log status periodically
        if self.candle_count % 10 == 0:
            LOGGER.info(self.mm_layer.format_status())

    def stop(self) -> None:
        """Stop the indicator."""
        LOGGER.info("Stopping MM indicator...")
        self.running = False

        if self.ws:
            asyncio.create_task(self.ws.close())

        # Close any open position at last price
        if self.mm_layer.inventory_tracker.has_position():
            if self.mm_layer.last_candle:
                self.mm_layer.close_position_manual(
                    exit_price=self.mm_layer.last_candle.close,
                    reason="SHUTDOWN"
                )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Binance Futures Market Maker with Gap Signal Bias"
    )

    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading symbol (default: BTCUSDT)"
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="5m",
        help="Candle timeframe (default: 5m)"
    )
    parser.add_argument(
        "--grid-levels",
        type=int,
        default=3,
        help="Number of grid levels per direction (default: 3)"
    )
    parser.add_argument(
        "--base-atr-mult",
        type=float,
        default=0.5,
        help="First grid level ATR multiplier (default: 0.5)"
    )
    parser.add_argument(
        "--atr-increment",
        type=float,
        default=0.5,
        help="ATR increment per level (default: 0.5)"
    )
    parser.add_argument(
        "--notional-per-level",
        type=float,
        default=100.0,
        help="USD per grid order (default: 100)"
    )
    parser.add_argument(
        "--atr-period",
        type=int,
        default=14,
        help="ATR calculation period (default: 14)"
    )
    parser.add_argument(
        "--maker-fee",
        type=float,
        default=0.00002,
        help="Maker fee rate (default: 0.00002 = 0.002%%)"
    )
    parser.add_argument(
        "--taker-fee",
        type=float,
        default=0.0002,
        help="Taker fee rate (default: 0.0002 = 0.02%%)"
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Disable grid refresh on fill"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Data output directory (default: data)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )

    return parser.parse_args()


async def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Create config from args
    config = GridConfig(
        num_levels=args.grid_levels,
        base_atr_multiplier=args.base_atr_mult,
        atr_increment=args.atr_increment,
        notional_per_level=args.notional_per_level,
        atr_period=args.atr_period,
        maker_fee_rate=args.maker_fee,
        taker_fee_rate=args.taker_fee,
        refresh_on_fill=not args.no_refresh,
    )

    # Determine data directory
    data_dir = Path(args.data_dir)

    LOGGER.info(
        f"Starting MM indicator: {args.symbol} {args.timeframe}, "
        f"levels={config.num_levels}, notional=${config.notional_per_level}/level, "
        f"ATR period={config.atr_period}, refresh={config.refresh_on_fill}"
    )

    # Create indicator
    indicator = BinanceMMIndicator(
        symbol=args.symbol,
        timeframe=args.timeframe,
        config=config,
        data_dir=data_dir,
    )

    # Setup signal handlers
    loop = asyncio.get_event_loop()

    def handle_signal(signum, frame):
        LOGGER.info(f"Received signal {signum}, shutting down...")
        indicator.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Start indicator
    try:
        await indicator.start()
    except KeyboardInterrupt:
        indicator.stop()
    finally:
        # Final stats
        stats = indicator.mm_layer.pnl_calculator.get_stats()
        LOGGER.info(
            f"Final stats: "
            f"Trades={stats['total_trades']}, "
            f"Win rate={stats['win_rate']:.1f}%, "
            f"P&L=${stats['cumulative_pnl']:.2f}, "
            f"Fees=${stats['cumulative_fees']:.4f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
