# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **External Gap Indicator** trading system - a real-time gap detection bot that streams Binance Futures WebSocket data to identify "external gaps" and execute simulated trades with position reversal logic.

**Key Differentiator:** Unlike traditional 3-candle FVG (Fair Value Gap) systems, this uses **candidate extreme tracking** to detect gaps earlier and more generally across all market conditions.

**Trading Strategy:** First-reversal entry logic with trend-following position management:
1. Bot launches → detects first gap → NO TRADE (waits for reversal)
2. Same polarity gaps → Telegram notifications only, NO TRADE
3. Opposite polarity gap detected → PENDING ENTRY created
4. Next candle opens → ENTRY EXECUTED at open price
5. Position held until opposite gap → CLOSE + REVERSE
6. 24-hour auto-close if no reversal occurs

**Current Implementation:** Bot runs on **2m timeframe** (not 5m) with $1000 notional, 3 bps fees each direction (6 bps total per round trip).

## Available Implementations

This repository contains **TWO types** of external gap systems:

### 1. Pure Detection Bots (RECOMMENDED FOR TESTING)

**Files:** `binance_extgap_detector_v1_simple.py` and `binance_extgap_detector_v2_corrected.py`

**Purpose:** Compare two candidate reset strategies without trade simulation.

**Key Features:**
- ✅ Pure gap detection (no trade manager, no P&L calculations)
- ✅ Telegram notifications (4 types: first gap, normal gap, reversal, hourly stats)
- ✅ CSV logging for analysis
- ✅ Lightweight and focused

**Differences:**
- **V1 (Simple):** After any gap → reset both candidates to current candle
  - `bearish_candidate = candle.low`
  - `bullish_candidate = candle.high`
- **V2 (Corrected):** After gap → reset candidates to opposite extreme (from PineScript analysis)
  - After bearish gap: `bearish_candidate = candle.high` (forces price to rise before next bearish gap)
  - After bullish gap: `bullish_candidate = candle.low` (forces price to drop before next bullish gap)

**Usage:**
```bash
# Start v1 (simple reset logic)
./start_extgap_detector.sh --version v1 --bg

# Start v2 (corrected reset logic)
./start_extgap_detector.sh --version v2 --bg

# Run both simultaneously for comparison
./start_extgap_detector.sh --version v1 --bg
./start_extgap_detector.sh --version v2 --bg

# Check status
./status_extgap_detector.sh

# Stop specific version
./stop_extgap_detector.sh --version v1

# Compare results
diff data/extgap_detector_v1_gaps.csv data/extgap_detector_v2_gaps.csv
```

**Output Files:**
- CSV: `data/extgap_detector_v1_gaps.csv` and `data/extgap_detector_v2_gaps.csv`
- Logs: `logs/extgap_detector_v1.log` and `logs/extgap_detector_v2.log`

**Telegram Notifications:**
1. **First gap:** Initial gap detected at startup (no trade recommendation)
2. **Normal gap:** Same polarity as previous gap
3. **Reversal:** Polarity changed (bullish→bearish or bearish→bullish) - potential entry signal
4. **Hourly stats:** Automatic summary every hour with gap counts and frequency

### 2. Full Trading Bots (PRODUCTION)

**Files:** `binance_extgap_indicator_2m.py` and `binance_extgap_indicator_5m.py`

**Purpose:** Complete trading system with gap detection + simulated position management.

**Key Features:**
- ✅ Gap detection + trade simulation
- ✅ Position reversal logic (close + open opposite)
- ✅ 24-hour auto-close failsafe
- ✅ P&L tracking with fee calculations (6 bps total)
- ✅ Trade history CSV

**Trading Logic:**
- First gap detected → NO TRADE (wait for reversal)
- Opposite polarity gap → PENDING ENTRY created
- Next candle opens → ENTRY EXECUTED at open price
- Same polarity gap → NO NEW TRADE (hold position)
- Opposite polarity gap → CLOSE + REVERSE position
- 24 hours elapsed → AUTO-CLOSE position

**Usage:**
```bash
./start_extgap_indicator.sh --timeframe 2m --bg
./stop_extgap_indicator.sh --timeframe 2m
tail -f logs/extgap_indicator_2m.log
```

## Core Architecture

### External Gap Detection Algorithm

The system tracks **candidate extremes** since the last gap:
- **Bearish Candidate**: Highest low since last gap
- **Bullish Candidate**: Lowest high since last gap

**Gap Detection Rules:**
- **Bullish Gap**: Current low > bullish_candidate_high (lowest high)
- **Bearish Gap**: Current high < bearish_candidate_low (highest low)

This is fundamentally different from 3-candle FVG:
- No fixed 3-candle window
- No expiry timer
- Detects gaps sooner
- More general across market conditions

### Code Structure (Single-File Architecture)

Both `binance_extgap_indicator_2m.py` and `binance_extgap_indicator_5m.py` contain ALL logic in a single file:

**Data Models** (lines 63-137):
- `Candle`: Closed kline data
- `ExternalGapDetection`: Gap event with first-gap flag
- `ExtGapTrade`: Open position (no SL/TP)
- `TradeResult`: Closed trade with P&L

**ExternalGapSymbolState** (lines 144-330):
- Tracks candle history (deque, maxlen=500)
- Maintains candidate extremes (bearish_candidate_low, bullish_candidate_high)
- Implements first-reversal logic (first_gap_detected, first_gap_polarity)
- **Pending entry system**: Sets pending_entry_side on reversal, executed next candle
- `add_candle()`: Core gap detection logic
- `get_pending_entry()`: Returns pending entry and clears state

**ExtGapTradeManager** (lines 337-554):
- One position per symbol
- `open_or_reverse()`: Closes opposite position, opens new position
- `check_24h_expiry()`: Auto-closes positions after 86400 seconds
- Fee calculation: 3 bps entry (0.02% fee + 0.01% slippage), 3 bps exit
- Tracks cumulative statistics (PnL, wins, losses, fees)

**CSV Recorders** (lines 556-646):
- `ExtGapRecorder`: Writes gap detections to CSV
- `TradeRecorder`: Writes trade results to CSV

**TelegramExtGapNotifier** (lines 648-833):
- `from_env()`: Loads credentials with timeframe fallback
  - Tries `TELEGRAM_BOT_TOKEN_EXTGAP_2M` first
  - Falls back to `TELEGRAM_BOT_TOKEN`
- Different notification messages for first gap vs reversal
- Shows P&L, cumulative P&L, win/loss ratio

**WebSocket Loop** (lines 882-1056):
- `listen_for_gaps()`: Main async loop
- `_handle_stream_message()`: Processes closed candles
- **Critical flow order**:
  1. Check 24h expiry first (lines 1007-1012)
  2. Execute pending entry from previous candle (lines 1014-1035)
  3. Detect new gap and set pending entry (lines 1037-1055)

### Important Implementation Details

**Entry Timing:**
- Gap detected at candle close time T
- Pending entry created with next_open price
- Next candle opens at time T (candle close = next candle open)
- Entry executes at open price of candle following detection candle

**24-Hour Auto-Close:**
- Timer starts from entry_time (not first candle analyzed)
- Checked on every closed candle before processing new entries
- Close reason: "24H_EXPIRY"
- Prevents indefinite positions if no reversal occurs

**Fee Structure (UPDATED - NOT 2 bips):**
- Entry: 0.0003 (3 bps) = 0.02% fee + 0.01% slippage
- Exit: 0.0003 (3 bps) = 0.02% fee + 0.01% slippage
- Total: 6 bps per round trip
- Applied to notional USD value, not quantity

**First-Reversal Logic:**
- `first_gap_detected` flag tracks if any gap seen
- `first_gap_polarity` tracks first gap direction
- `is_first_gap` flag in ExternalGapDetection marks first gap
- Only reversal gaps (opposite polarity) create pending entries
- Prevents trading on random initial gaps

## Common Commands

### Start Bot (Background Mode - Recommended)
```bash
./start_extgap_indicator.sh --timeframe 2m --bg
./start_extgap_indicator.sh --timeframe 5m --symbol ETHUSDT --bg
./start_extgap_indicator.sh --timeframe 2m --notional 2000 --instance AWS --bg
```

### Start Bot (Foreground Mode - Testing)
```bash
./start_extgap_indicator.sh --timeframe 2m
python3 binance_extgap_indicator_2m.py --log-level DEBUG
```

### Stop Bot
```bash
./stop_extgap_indicator.sh --timeframe 2m
./stop_extgap_indicator.sh --timeframe 5m
```

### Check Status
```bash
./status_extgap_indicator.sh
./status_extgap_indicator.sh 2m
```

### Monitor Logs
```bash
# Live logs
tail -f logs/extgap_indicator_2m.log

# Filter errors
tail -f logs/extgap_indicator_2m.log | grep ERROR

# Recent gap detections
grep "gap detected" logs/extgap_indicator_2m.log | tail -20

# Recent trades
grep "Entry Executed\|Position Closed" logs/extgap_indicator_2m.log | tail -20
```

### View Data Files
```bash
# Gap detections
tail -20 data/binance_extgap_2m_gaps.csv

# Trade results
tail -20 data/binance_extgap_2m_trades.csv

# Count gaps by polarity
grep -c "bullish" data/binance_extgap_2m_gaps.csv
grep -c "bearish" data/binance_extgap_2m_gaps.csv

# Win/loss ratio
grep -c "WIN" data/binance_extgap_2m_trades.csv
grep -c "LOSS" data/binance_extgap_2m_trades.csv
```

### Restart Bot with Clean State
```bash
# Stop bot
./stop_extgap_indicator.sh --timeframe 2m

# Remove stale PID if needed
rm -f binance_extgap_indicator_2m.pid

# Start bot
./start_extgap_indicator.sh --timeframe 2m --bg
```

## Environment Configuration

### Required Variables in Parent `.env`
```bash
# Pure Detection Bots (v1/v2 comparison - RECOMMENDED FOR TESTING)
TELEGRAM_BOT_TOKEN_EXTGAP_DETECTOR=8586866654:AAF6hoImqAM46hhsfEFm0898ZNpFTqEZGKw
TELEGRAM_CHAT_IDS_EXTGAP_DETECTOR=1474566688,-1003358731201

# Full Trading Bots (2m timeframe - PRODUCTION)
TELEGRAM_BOT_TOKEN_EXTGAP_2M=8586866654:AAF6hoImqAM46hhsfEFm0898ZNpFTqEZGKw
TELEGRAM_CHAT_IDS_EXTGAP_2M=1474566688,-1003358731201

# Full Trading Bots (5m timeframe - LEGACY)
TELEGRAM_BOT_TOKEN_EXTGAP_5M=8146581274:AAH9AzQzhttftcaiJbrnyRkUY4z2ZOpQJd0
TELEGRAM_CHAT_IDS_EXTGAP_5M=1474566688,-1002985538408

# Instance identification
INSTANCE_ID=LOCAL  # Or AWS, REPLIT, etc.
```

**Credential Loading Priority:**
1. Timeframe-specific token (e.g., `TELEGRAM_BOT_TOKEN_EXTGAP_2M`)
2. Generic token fallback (`TELEGRAM_BOT_TOKEN`)
3. Same logic for chat IDs

## Development Workflow

### Modifying Trade Logic

**Key Functions to Edit:**

1. **Gap Detection** - `ExternalGapSymbolState.add_candle()` (lines ~186-312)
   - Candidate tracking logic
   - Gap detection conditions
   - First-reversal logic
   - Pending entry creation

2. **Position Management** - `ExtGapTradeManager.open_or_reverse()` (lines ~373-426)
   - Entry/exit logic
   - Fee calculations
   - Position sizing

3. **Auto-Close Logic** - `ExtGapTradeManager.check_24h_expiry()` (lines ~508-534)
   - Time-based position closure
   - Expiry threshold (currently 86400 seconds)

4. **Entry Execution** - `_handle_stream_message()` (lines ~1014-1035)
   - Pending entry retrieval and execution
   - Order of operations (24h check → pending entry → gap detection)

### Adding New Timeframes

**IMPORTANT:** Don't modify existing files. Create new timeframe-specific files.

1. Copy existing script:
   ```bash
   cp binance_extgap_indicator_2m.py binance_extgap_indicator_15m.py
   ```

2. Update default timeframe in `parse_args()` (line ~1146):
   ```python
   parser.add_argument("--timeframe", default="15m", ...)
   ```

3. Update default output paths (lines ~1153, 1160):
   ```python
   parser.add_argument("--output", default="data/binance_extgap_15m_gaps.csv", ...)
   parser.add_argument("--trades-output", default="data/binance_extgap_15m_trades.csv", ...)
   ```

4. Update log file path in `setup_logging()` (line ~1207):
   ```python
   logging.FileHandler("binance_extgap_indicator_15m.log")
   ```

5. Update Telegram token in `from_env()` (lines ~681-686):
   ```python
   bot_token = os.getenv("TELEGRAM_BOT_TOKEN_EXTGAP_15M") or os.getenv("TELEGRAM_BOT_TOKEN")
   chat_ids_str = os.getenv("TELEGRAM_CHAT_IDS_EXTGAP_15M") or os.getenv("TELEGRAM_CHAT_IDS")
   ```

6. Add credentials to parent `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN_EXTGAP_15M=your_token
   TELEGRAM_CHAT_IDS_EXTGAP_15M=your_chat_ids
   ```

7. Test new timeframe:
   ```bash
   ./start_extgap_indicator.sh --timeframe 15m --bg
   ```

### Updating Fee Rates

**Current Fees:** 3 bps (0.03%) each direction

To modify fees:

1. Update constants (lines ~58-59):
   ```python
   DEFAULT_ENTRY_FEE_RATE = 0.0003  # 0.03%
   DEFAULT_EXIT_FEE_RATE = 0.0003  # 0.03%
   ```

2. Fee calculation in `_close_position()` (lines ~449-451):
   ```python
   exit_fee = trade.position_size_usd * self.exit_fee_rate
   total_fees = trade.entry_fee + exit_fee
   net_pnl = gross_pnl - total_fees
   ```

### Testing Changes

**Always test in foreground mode first:**
```bash
# Stop production bot
./stop_extgap_indicator.sh --timeframe 2m

# Run in foreground with debug logging
python3 binance_extgap_indicator_2m.py --log-level DEBUG

# Watch for errors and validate behavior
# Ctrl+C to stop

# If all good, restart in background
./start_extgap_indicator.sh --timeframe 2m --bg
```

## Troubleshooting

### Bot Won't Start - PID File Exists
```bash
# Check if process actually running
ps -p $(cat binance_extgap_indicator_2m.pid)

# If not running, remove stale PID
rm binance_extgap_indicator_2m.pid

# Restart
./start_extgap_indicator.sh --timeframe 2m --bg
```

### No Telegram Notifications
```bash
# Check credentials loaded
python3 -c "import os; from dotenv import load_dotenv; load_dotenv('../.env'); print('2M Token:', os.getenv('TELEGRAM_BOT_TOKEN_EXTGAP_2M')); print('Chat IDs:', os.getenv('TELEGRAM_CHAT_IDS_EXTGAP_2M'))"

# Check logs for Telegram errors
grep "Telegram\|telegram" logs/extgap_indicator_2m.log | tail -20

# Verify bot token with Telegram API
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

### No Gaps Detected
This is normal behavior! External gaps require specific market conditions:
- Need clear trend direction
- Sufficient volatility
- Price must break beyond candidate extremes

**To increase gap frequency:**
- Try more volatile symbols (SOLUSDT, ETHUSDT)
- Use shorter timeframes (2m instead of 5m)
- Increase symbol count (modify script to track multiple symbols)

### WebSocket Disconnections
The bot auto-reconnects with exponential backoff (1s → 60s max). Check logs:
```bash
grep "WebSocket\|Reconnecting" logs/extgap_indicator_2m.log | tail -20
```

If persistent disconnections:
- Check network connectivity: `ping fstream.binance.com`
- Verify Binance API accessible: `curl https://fapi.binance.com/fapi/v1/ping`
- Check for rate limiting in logs

### Position Stuck - Not Closing
Two exit mechanisms:
1. **Reversal signal**: Opposite gap detected
2. **24-hour auto-close**: Failsafe if no reversal

Check position age:
```bash
# View last trade entry time
tail -1 data/binance_extgap_2m_trades.csv
```

Manually close if needed (modify script to add manual close command).

## Data Analysis

### CSV File Formats

**Gap Detections CSV:**
```csv
detected_at_utc,symbol,polarity,gap_level,gap_opening_bar_time,detection_bar_time
2025-11-11T18:52:00+00:00,BTCUSDT,bullish,103459.50,2025-11-11T17:35:00+00:00,2025-11-11T18:52:00+00:00
```

**Trade Results CSV:**
```csv
Status,Open Time,Close Time,Market,Side,Entry Price,Exit Price,Position Size ($),Position Size (Qty),Gross P&L,Realized P&L,Total Fees,Close Reason,Cumulative Wins,Cumulative Losses,Cumulative P&L,Cumulative Fees
WIN,2025-11-11T16:24:59+00:00,2025-11-11T17:34:59+00:00,BTCUSDT,SHORT,104111.20,103432.20,1000.00,0.009605,6.52,5.92,0.60,REVERSE,1,0,5.92,0.60
```

### Performance Metrics

**Win Rate:**
```bash
wins=$(grep -c "WIN" data/binance_extgap_2m_trades.csv)
losses=$(grep -c "LOSS" data/binance_extgap_2m_trades.csv)
echo "Win Rate: $(echo "scale=2; $wins / ($wins + $losses) * 100" | bc)%"
```

**Cumulative P&L:**
```bash
tail -1 data/binance_extgap_2m_trades.csv | awk -F',' '{print "P&L: $" $16 " | Fees: $" $17}'
```

**Gap Frequency:**
```bash
echo "Total gaps: $(wc -l < data/binance_extgap_2m_gaps.csv)"
echo "Bullish: $(grep -c "bullish" data/binance_extgap_2m_gaps.csv)"
echo "Bearish: $(grep -c "bearish" data/binance_extgap_2m_gaps.csv)"
```

## Critical Differences from 3-Candle FVG System

| Feature | External Gap | 3-Candle FVG (scripts dir) |
|---------|-------------|---------------------------|
| Detection | Candidate extremes | Fixed 3-candle pattern |
| Timing | Earlier (1-2 candles sooner) | Only after 3 candles |
| Expiry | On new gap (no time limit) | 3 candles max |
| Entry | Next candle open after gap | Gap rejection (price returns to gap) |
| Exit | Reverse signal OR 24h auto-close | ATR-based SL/TP |
| Filters | None (pure price action) | ATR directional + Heikin Ashi |
| Position Management | One at a time, reverse on signal | Multiple concurrent positions |
| First Gap Behavior | Wait for reversal (no trade) | Trade immediately on rejection |

## Security and Safety

- **Simulated trading only** - No real funds at risk
- No Binance API keys needed (read-only WebSocket)
- Telegram tokens in `.env` must be kept secure
- PID files prevent duplicate instances
- No git commits of `.env` file
- Log files may contain sensitive data (Telegram IDs)

## Performance Characteristics

- **CPU Usage**: ~1-2% (single symbol, 2m timeframe)
- **Memory Usage**: ~50-80MB (deque maxlen=500 candles)
- **WebSocket Latency**: <100ms typical
- **Gap Detection**: O(1) per candle (candidate tracking)
- **CSV Writes**: Append-only, negligible impact
- **Telegram API**: Async, non-blocking

## Related Documentation

- `README.md` - Comprehensive strategy explanation
- `QUICKSTART.md` - Step-by-step startup guide
- `COMMANDS.txt` - Complete command reference for WSL
- Parent `CLAUDE.md` - Main project architecture (Paradex trading system)
- `../scripts/CLAUDE.md` - 3-candle FVG gap indicators (different strategy)
