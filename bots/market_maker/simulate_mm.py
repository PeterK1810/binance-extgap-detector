#!/usr/bin/env python3
"""Quick simulation of Market Maker strategy using historical data.

Fetches historical candles from Binance and runs them through the MM execution layer.

Usage:
    python bots/market_maker/simulate_mm.py --symbol BTCUSDT --timeframe 5m --candles 200
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone

import aiohttp

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bots.indicators.binance_extgap_indicator_5m import Candle, ExternalGapSymbolState
from bots.market_maker.models import GridConfig
from bots.market_maker.mm_execution_layer import MarketMakerExecutionLayer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("mm_simulator")

BINANCE_FUTURES_API = "https://fapi.binance.com"


async def fetch_historical_klines(symbol: str, interval: str, limit: int = 200) -> list[Candle]:
    """Fetch historical klines from Binance Futures REST API."""
    url = f"{BINANCE_FUTURES_API}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch klines: {resp.status}")

            data = await resp.json()

            candles = []
            for kline in data[:-1]:  # Exclude last (incomplete) candle
                candle = Candle(
                    open_time_ms=int(kline[0]),
                    close_time_ms=int(kline[6]),
                    open=float(kline[1]),
                    high=float(kline[2]),
                    low=float(kline[3]),
                    close=float(kline[4]),
                )
                candles.append(candle)

            return candles


def run_simulation(
    symbol: str,
    candles: list[Candle],
    config: GridConfig,
    data_dir: Path,
    timeframe: str,
) -> dict:
    """Run market maker simulation on historical candles."""

    # Initialize components
    symbol_state = ExternalGapSymbolState(symbol)
    mm_layer = MarketMakerExecutionLayer(
        symbol_state=symbol_state,
        config=config,
        data_dir=data_dir,
        timeframe=timeframe,
    )

    LOGGER.info(f"Running simulation on {len(candles)} candles...")
    LOGGER.info(f"Price range: {min(c.low for c in candles):.2f} - {max(c.high for c in candles):.2f}")
    LOGGER.info(f"Time range: {candles[0].close_time} to {candles[-1].close_time}")
    LOGGER.info("-" * 60)

    gaps_detected = 0
    fills_count = 0

    for i, candle in enumerate(candles):
        # Check 24h expiry
        mm_layer.check_24h_expiry(candle)

        # Process candle
        gap = mm_layer.process_candle(candle)

        if gap:
            gaps_detected += 1
            LOGGER.info(
                f"[{candle.close_time.strftime('%H:%M')}] "
                f"{'BULLISH' if gap.polarity == 'bullish' else 'BEARISH'} gap #{gap.sequence_number} "
                f"@ {gap.gap_level:.2f}"
            )

        # Log fills
        if mm_layer.grid_state.filled_orders > fills_count:
            new_fills = mm_layer.grid_state.filled_orders - fills_count
            fills_count = mm_layer.grid_state.filled_orders

            inv = mm_layer.inventory_tracker
            if inv.has_position():
                pos = inv.current_inventory
                LOGGER.info(
                    f"[{candle.close_time.strftime('%H:%M')}] "
                    f"+{new_fills} fill(s) -> {pos.side} {pos.total_quantity:.6f} @ {pos.average_entry_price:.2f}"
                )

        # Log status every 50 candles
        if (i + 1) % 50 == 0:
            LOGGER.info(f"Processed {i+1}/{len(candles)} candles...")

    # Close any open position at end
    if mm_layer.inventory_tracker.has_position():
        mm_layer.close_position_manual(
            exit_price=candles[-1].close,
            reason="SIMULATION_END"
        )
        LOGGER.info(f"Closed position at simulation end: {candles[-1].close:.2f}")

    return mm_layer.get_stats()


def format_results(stats: dict) -> str:
    """Format simulation results for display."""
    pnl = stats['pnl']
    grid = stats['grid']

    # Calculate total orders
    total_orders = grid['filled_orders'] + grid['pending_orders'] + grid['cancelled_orders']
    fill_rate = grid['filled_orders'] / max(total_orders, 1) * 100

    lines = [
        "",
        "=" * 60,
        "SIMULATION RESULTS",
        "=" * 60,
        "",
        f"Symbol: {stats['symbol']}",
        "",
        "TRADING PERFORMANCE:",
        f"  Total trades: {pnl['total_trades']}",
        f"  Wins: {pnl['winning_trades']} | Losses: {pnl['losing_trades']}",
        f"  Win rate: {pnl['win_rate']:.1f}%",
        f"  Avg P&L per trade: ${pnl['avg_pnl_per_trade']:.2f}",
        f"  Cumulative P&L: ${pnl['cumulative_pnl']:.2f}",
        f"  Total fees: ${pnl['cumulative_fees']:.4f}",
        f"  Profit factor: {pnl['profit_factor']:.2f}",
        "",
        "GRID ACTIVITY:",
        f"  Orders filled: {grid['filled_orders']}",
        f"  Orders cancelled: {grid['cancelled_orders']}",
        f"  Orders pending: {grid['pending_orders']}",
        f"  Fill rate: {fill_rate:.1f}%",
        "",
        "FILL STATISTICS:",
        f"  Total fills: {pnl['total_fills']}",
        f"  Avg win: ${pnl['avg_win']:.2f}",
        f"  Avg loss: ${pnl['avg_loss']:.2f}",
        "",
        "=" * 60,
    ]
    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Market Maker Simulation")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading symbol")
    parser.add_argument("--timeframe", default="5m", help="Candle timeframe")
    parser.add_argument("--candles", type=int, default=200, help="Number of candles to simulate")
    parser.add_argument("--grid-levels", type=int, default=3, help="Grid levels")
    parser.add_argument("--notional", type=float, default=100.0, help="USD per grid level")
    parser.add_argument("--atr-period", type=int, default=14, help="ATR period")
    args = parser.parse_args()

    LOGGER.info("=" * 60)
    LOGGER.info("MARKET MAKER SIMULATION")
    LOGGER.info("=" * 60)
    LOGGER.info(f"Symbol: {args.symbol}")
    LOGGER.info(f"Timeframe: {args.timeframe}")
    LOGGER.info(f"Candles: {args.candles}")
    LOGGER.info(f"Grid levels: {args.grid_levels}")
    LOGGER.info(f"Notional/level: ${args.notional}")
    LOGGER.info("=" * 60)

    # Fetch historical data
    LOGGER.info("Fetching historical candles from Binance...")
    candles = await fetch_historical_klines(args.symbol, args.timeframe, args.candles)
    LOGGER.info(f"Fetched {len(candles)} closed candles")

    # Create config
    config = GridConfig(
        num_levels=args.grid_levels,
        base_atr_multiplier=0.5,
        atr_increment=0.5,
        notional_per_level=args.notional,
        atr_period=args.atr_period,
        maker_fee_rate=0.00002,  # 0.002%
        taker_fee_rate=0.0002,   # 0.02%
        refresh_on_fill=True,
    )

    # Create data directory for simulation output
    data_dir = Path("data/simulation")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Run simulation
    stats = run_simulation(
        symbol=args.symbol,
        candles=candles,
        config=config,
        data_dir=data_dir,
        timeframe=args.timeframe,
    )

    # Display results
    print(format_results(stats))


if __name__ == "__main__":
    asyncio.run(main())
