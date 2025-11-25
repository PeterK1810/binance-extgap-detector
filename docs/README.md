# Binance External Gap Detector

Real-time gap detection system for cryptocurrency trading using Binance Futures WebSocket data. Implements the **External Gap** algorithm - a more general and earlier gap detection method than traditional 3-candle Fair Value Gap (FVG) patterns.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Features

- **V3 PineScript Algorithm** - Exact port of "[THE] eG v2" TradingView indicator with group-based candidate tracking
- **Real-time Detection** - WebSocket streaming from Binance Futures (no API key required)
- **Interactive Configuration** - Choose symbol, timeframe, and stats interval at startup
- **Trade Simulation** - Calculate hypothetical P&L with configurable fees and position sizing
- **Telegram Notifications** - Real-time alerts for gap detection and trade signals
- **CSV Logging** - Complete history of gaps and simulated trades
- **Multiple Versions** - Compare V1 (simple), V2 (corrected), and V3 (PineScript) algorithms
- **Full Trading Bots** - Production-ready bots with position management (2m/5m timeframes)

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/PeterK1810/binance-extgap-detector.git
cd binance-extgap-detector

# Install dependencies
pip install -r requirements.txt

# Or use uv for faster installation (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv pip install -r requirements.txt
```

### 2. Configuration

```bash
# Create environment file from template
cp .env.example .env

# Edit .env and add your Telegram credentials
nano .env  # or vim, code, etc.
```

Required environment variables:
```bash
TELEGRAM_BOT_TOKEN_EXTGAP_DETECTOR=your_bot_token_here
TELEGRAM_CHAT_IDS_EXTGAP_DETECTOR=123456789,-1001234567890
```

Get your Telegram bot token from [@BotFather](https://t.me/BotFather) and chat ID from [@userinfobot](https://t.me/userinfobot).

### 3. Run V3 Detector

```bash
# Run V3 PineScript detector (recommended)
python3 binance_extgap_detector_v3_pinescript.py

# Interactive prompts will ask for:
# - Symbol (e.g., BTCUSDT, ETHUSDT, SOLUSDT)
# - Timeframe (e.g., 1m, 3m, 5m, 15m, 1h)
# - Stats interval (e.g., 10m, 30m, 1h, 2h, 4h)
```

**Example session:**
```
Enter symbol (default BTCUSDT):
Enter timeframe (default 1m): 5m
Enter stats interval (default 1h): 30m

Starting External Gap Detector V3...
Symbol: BTCUSDT | Timeframe: 5m | Stats: every 30m
WebSocket connected to Binance Futures
Waiting for first candle close...
```

## Replit Deployment (24/7 Operation)

The **V3 Replit Edition** (`binance_extgap_detector_v3_replit.py`) is optimized for 24/7 deployment on Replit Reserved VMs with command-line arguments instead of interactive prompts.

### Why Use Replit?

- ✅ **24/7 uptime** with Reserved VM ($20-30/month)
- ✅ **No infrastructure management** - just click Run
- ✅ **Built-in secrets management** - secure Telegram credentials
- ✅ **Easy parameter changes** - edit `.replit` file without code changes
- ✅ **Multiple instances** - run different symbols/timeframes on separate Repls

### Prerequisites

1. **Replit Account** - Sign up at [replit.com](https://replit.com)
2. **Reserved VM** - Required for 24/7 operation (free tier sleeps after inactivity)
3. **Telegram Bot** - Get token from [@BotFather](https://t.me/BotFather)
4. **Chat ID** - Get from [@userinfobot](https://t.me/userinfobot)

### Step-by-Step Deployment

#### 1. Fork/Import Repository to Replit

```bash
# Option A: Import from GitHub
1. Go to Replit.com
2. Click "Create Repl"
3. Select "Import from GitHub"
4. Paste: https://github.com/PeterK1810/binance-extgap-detector
5. Select "paradex_extgap" directory as root

# Option B: Clone manually
git clone https://github.com/PeterK1810/binance-extgap-detector.git
cd paradex_extgap
```

#### 2. Configure Replit Secrets

Navigate to **Tools** → **Secrets** in Replit and add:

```
TELEGRAM_BOT_TOKEN_EXTGAP_DETECTOR = your_bot_token_here
TELEGRAM_CHAT_IDS_EXTGAP_DETECTOR = 123456789,-1001234567890
INSTANCE_ID = REPLIT  # Optional: helps identify which instance sent notifications
```

**Important:** Replit Secrets are automatically injected as environment variables - no `.env` file needed!

#### 3. Configure Run Parameters

Edit the `.replit` file to set your desired configuration:

```toml
# Default configuration (BTCUSDT, 2m timeframe, 1h stats)
run = ["python3", "binance_extgap_detector_v3_replit.py", "--symbol", "BTCUSDT", "--timeframe", "2m", "--stats-interval", "1h"]

# Example: ETHUSDT on 5m timeframe with 30m stats
run = ["python3", "binance_extgap_detector_v3_replit.py", "--symbol", "ETHUSDT", "--timeframe", "5m", "--stats-interval", "30m"]

# Example: SOLUSDT on 3m timeframe with debug logging
run = ["python3", "binance_extgap_detector_v3_replit.py", "--symbol", "SOLUSDT", "--timeframe", "3m", "--stats-interval", "1h", "--log-level", "DEBUG"]
```

#### 4. Install Dependencies

Replit auto-installs from `requirements.txt`, but you can manually trigger:

```bash
pip install -r requirements.txt
```

Or use the Shell tab:
```bash
python3 -m pip install websockets aiohttp python-dotenv
```

#### 5. Run the Bot

Click the **Run** button in Replit, or use the Shell:

```bash
python3 binance_extgap_detector_v3_replit.py --symbol BTCUSDT --timeframe 2m --stats-interval 1h
```

#### 6. Enable 24/7 Operation (Reserved VM)

1. Go to Replit → **Resources** → **Reserved VM**
2. Subscribe to Reserved VM plan ($20-30/month)
3. Bot will run continuously without sleep

**Note:** Free tier Repls sleep after 5 minutes of inactivity. Reserved VM is required for true 24/7 operation.

### Multi-Timeframe Setup (Multiple Repls)

To monitor multiple symbols or timeframes simultaneously:

1. **Create separate Repl for each configuration:**
   - Repl 1: `binance-extgap-btc-2m` → BTCUSDT 2m
   - Repl 2: `binance-extgap-eth-5m` → ETHUSDT 5m
   - Repl 3: `binance-extgap-sol-3m` → SOLUSDT 3m

2. **Each Repl has its own `.replit` config:**
   ```toml
   # Repl 1: BTCUSDT 2m
   run = ["python3", "binance_extgap_detector_v3_replit.py", "--symbol", "BTCUSDT", "--timeframe", "2m", "--stats-interval", "1h"]

   # Repl 2: ETHUSDT 5m
   run = ["python3", "binance_extgap_detector_v3_replit.py", "--symbol", "ETHUSDT", "--timeframe", "5m", "--stats-interval", "1h"]

   # Repl 3: SOLUSDT 3m
   run = ["python3", "binance_extgap_detector_v3_replit.py", "--symbol", "SOLUSDT", "--timeframe", "3m", "--stats-interval", "1h"]
   ```

3. **All Repls share same Telegram credentials** (or use different bots for different Repls)

### Command-Line Options (V3 Replit)

```bash
python3 binance_extgap_detector_v3_replit.py --help

Options:
  --symbol SYMBOL           Trading symbol (default: BTCUSDT)
                           Examples: ETHUSDT, SOLUSDT, BNBUSDT

  --timeframe TIMEFRAME     Timeframe for gap detection (default: 2m)
                           Examples: 1m, 2m, 3m, 5m, 15m, 1h

  --stats-interval INTERVAL Statistics notification interval (default: 1h)
                           Examples: 10m, 30m, 1h, 2h, 4h

  --log-level LEVEL         Logging level (default: INFO)
                           Choices: DEBUG, INFO, WARNING, ERROR
```

### Monitoring Your Replit Bot

**View Logs:**
- Click **Console** tab in Replit to see real-time logs
- Look for: "✅ WebSocket connected", "🚨 GAP DETECTED", "📊 STATISTIQUES"

**Check Telegram:**
- Startup notification confirms bot is running
- Gap detections arrive in real-time
- Hourly stats keep you informed of performance

**CSV Data:**
- Navigate to `data/` folder in Replit file explorer
- Download `extgap_v3_btcusdt_2m_gaps.csv` for gap history
- Download `extgap_v3_btcusdt_2m_trades.csv` for P&L tracking

### Replit vs Local Deployment

| Feature | Replit Reserved VM | Local/VPS |
|---------|-------------------|-----------|
| **24/7 Uptime** | ✅ Built-in | ⚠️ Requires always-on machine |
| **Setup Time** | ⚡ 5 minutes | 🕒 15-30 minutes |
| **Cost** | $20-30/month | Free (electricity) or $5-10/month VPS |
| **Secrets Management** | ✅ Replit Secrets | ⚙️ Manual `.env` file |
| **Auto-Restart** | ✅ Yes | ⚠️ Requires systemd/screen |
| **Multi-Instance** | ✅ Easy (multiple Repls) | ⚙️ Manual process management |
| **Code Changes** | ✅ Edit in browser | 💻 Local editor + git push |

### Troubleshooting Replit Deployment

**Bot sleeps after 5 minutes:**
- ❌ You're on free tier (requires HTTP traffic to stay awake)
- ✅ Upgrade to Reserved VM for true 24/7 operation

**No Telegram notifications:**
- Check Replit Secrets are set: `TELEGRAM_BOT_TOKEN_EXTGAP_DETECTOR`, `TELEGRAM_CHAT_IDS_EXTGAP_DETECTOR`
- Verify token with: `curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe`
- Check Console logs for "✅ Telegram notifications enabled"

**Dependencies not installing:**
- Click **Shell** tab and run: `pip install -r requirements.txt`
- Check `replit.nix` has Python 3.11: `pkgs.python311`

**Want to change timeframe without restarting:**
- Edit `.replit` file → change `--timeframe` parameter
- Click **Stop** then **Run** to apply changes
- Bot will create new CSV files for the new timeframe

### Cost Optimization

**Single Reserved VM:**
- Run 1 symbol/timeframe: $20-30/month
- Recommended for focused strategy testing

**Multiple Symbols on One Repl:**
- Modify code to track multiple symbols concurrently (advanced)
- More complex but saves on Reserved VM cost

**Hybrid Approach:**
- Run BTCUSDT on Replit (most important)
- Run ETHUSDT/SOLUSDT on local machine or cheap VPS
- Balance cost vs convenience

## Algorithm Overview

### What is an External Gap?

The **External Gap** algorithm tracks **candidate extremes** since the last gap:
- **Bullish Candidate**: Lowest high since last gap
- **Bearish Candidate**: Highest low since last gap

A new gap forms when:
- **Bullish Gap**: Current candle's low breaks above the bullish candidate (lowest high)
- **Bearish Gap**: Current candle's high breaks below the bearish candidate (highest low)

### V3 PineScript Algorithm (Group-Based)

**How it works:**
1. Maintains a **group** (deque) of all candles since last gap
2. Calculates candidates from group extremes:
   - `bearish_candidate_low` = max of all lows in group
   - `bullish_candidate_high` = min of all highs in group
3. On gap detection:
   - **Cleans group** - removes candles ≤ gap opening candle
   - **Recalculates candidates** from remaining candles
4. Tracks **sequence numbers** (BULLISH #1, #2, #3... resets on reversal)

This mirrors the TradingView PineScript "[THE] eG v2" indicator exactly.

### Why External Gaps vs 3-Candle FVG?

| Feature | External Gap | 3-Candle FVG |
|---------|-------------|--------------|
| **Detection Speed** | Faster (1-2 candles sooner) | Requires 3 candles |
| **Market Conditions** | Works in all conditions | More specific patterns |
| **Expiry** | On new gap (no time limit) | Fixed 3-candle expiry |
| **False Positives** | Lower (candidate tracking) | Higher (fixed pattern) |
| **Complexity** | Moderate (stateful) | Low (pattern matching) |

## Trading Strategy

### First-Reversal Entry Logic

The system implements a **first-reversal** strategy to avoid trading random initial gaps:

1. **Bot launches** → Detects first gap → ⏳ **NO TRADE** (wait for reversal)
2. **Same polarity gaps** → 📢 Telegram notifications only, **NO TRADE**
3. **Opposite polarity gap** → 🚨 **PENDING ENTRY** created
4. **Next candle opens** → ✅ **ENTRY EXECUTED** at open price
5. **Position held** until opposite gap → 🔄 **CLOSE + REVERSE**
6. **24-hour auto-close** if no reversal occurs (trading bots only)

**Example Flow:**
```
1. Bot starts → Detects BULLISH gap at $67,000 → NO TRADE (first gap)
2. Price rises → Detects BULLISH #2 at $67,500 → NO TRADE (same polarity)
3. Price drops → Detects BEARISH gap at $68,500 → PENDING SHORT ENTRY (reversal!)
4. Next candle opens → SHORT ENTRY EXECUTED at open price
5. Price drops → Detects BEARISH #2 at $66,200 → NO NEW TRADE (hold position)
6. Price rises → Detects BULLISH gap at $67,200 → CLOSE SHORT + LONG ENTRY (reverse)
```

### Position Management (Trading Bots)

- **One position per symbol** at a time
- **Entry timing**: Next candle open after gap detection
- **Exit conditions**:
  - Reverse signal (opposite polarity gap)
  - 24-hour auto-close (failsafe)
- **No stop loss / take profit** - pure trend-following
- **Fee structure**:
  - Entry: 3 bps (0.03%) = 0.02% fee + 0.01% slippage
  - Exit: 3 bps (0.03%) = 0.02% fee + 0.01% slippage
  - Total: 6 bps per round trip

## Repository Structure

```
binance-extgap-detector/
├── binance_extgap_detector_v3_pinescript.py   ⭐ Main detector (recommended)
├── binance_extgap_v3_trading.py               V3 with trading logic
├── binance_extgap_indicator_2m.py             Full trading bot (2m)
├── binance_extgap_indicator_5m.py             Full trading bot (5m)
├── start_extgap_detector.sh                   Start detector scripts
├── stop_extgap_detector.sh                    Stop detector scripts
├── status_extgap_detector.sh                  Check detector status
├── start_extgap_indicator.sh                  Start trading bots
├── stop_extgap_indicator.sh                   Stop trading bots
├── status_extgap_indicator.sh                 Check trading bot status
├── requirements.txt                           Python dependencies
├── .env.example                               Environment template
├── README.md                                  This file
├── QUICKSTART.md                              Quick start guide
├── CLAUDE.md                                  Architecture documentation
├── TESTING_V3.md                              V3 testing guide
├── TROUBLESHOOTING_NO_GAPS.md                Troubleshooting guide
├── COMMANDS.txt                               Complete command reference
├── data/                                      CSV outputs (gitignored)
│   ├── extgap_v3_{symbol}_{tf}_gaps.csv
│   └── extgap_v3_{symbol}_{tf}_trades.csv
└── logs/                                      Log files (gitignored)
    └── extgap_v3_{symbol}_{tf}.log
```

## Available Scripts

### V3 PineScript Detector (Recommended)

**Pure detection with trade simulation:**
```bash
# Interactive mode
python3 binance_extgap_detector_v3_pinescript.py

# Command-line arguments
python3 binance_extgap_detector_v3_pinescript.py \
  --symbol ETHUSDT \
  --timeframe 5m \
  --stats-interval 1h \
  --notional 2000 \
  --log-level INFO
```

**Features:**
- Group-based candidate tracking (PineScript algorithm)
- Interactive configuration prompts
- Sequence numbering (BULLISH #1, #2, #3...)
- Trade simulation with P&L calculations
- Configurable stats intervals
- Dynamic output file paths

### V3 Trading Bot

**Live trading with position management:**
```bash
# Background mode
./start_extgap_indicator.sh --timeframe 2m --bg

# Foreground mode for testing
python3 binance_extgap_indicator_2m.py --symbol BTCUSDT
```

**Features:**
- All V3 detector features +
- Actual position tracking
- 24-hour auto-close failsafe
- Position reversal logic
- Fee-inclusive P&L tracking

### Comparison: V1 vs V2 vs V3

| Version | Algorithm | Candidate Reset | Use Case |
|---------|-----------|----------------|----------|
| **V1** | Simple reset | Both candidates → current candle | Testing baseline |
| **V2** | Corrected reset | Opposite extreme reset | Reduce false positives |
| **V3** | Group-based | Clean group + recalculate | Production (most accurate) |

Run multiple versions in parallel to compare:
```bash
# V3 in one terminal
python3 binance_extgap_detector_v3_pinescript.py

# Compare results
diff data/extgap_v3_btcusdt_5m_gaps.csv data/extgap_v1_gaps.csv
```

## Telegram Notifications

### Startup Notification
```
🚀 External Gap Detector V3 Started
Instance: LOCAL
Symbol: BTCUSDT
Timeframe: 5m
Stats Interval: 1h
Position Size: $1000
Fees: Entry 3bps | Exit 3bps
Status: Waiting for gaps...
```

### First Gap Detection (No Trade)
```
🔵 BULLISH External Gap #1
Symbol: BTCUSDT
Gap Level: $67,250.00
───────────────
📊 Gap Formation:
Candidate: 2025-11-16 14:35 UTC
Detected: 2025-11-16 16:15 UTC
Duration: 1h 40m
───────────────
⏳ Waiting for reversal to start trading
```

### Reversal Detection (Pending Entry)
```
🔴 BEARISH External Gap (Reversal from BULLISH #2)
Symbol: BTCUSDT
Gap Level: $68,500.00
───────────────
📊 Gap Formation:
Candidate: 2025-11-16 18:20 UTC
Detected: 2025-11-16 19:45 UTC
Duration: 1h 25m
───────────────
💰 Simulated Trade:
Side: SHORT
Entry (next open): ~$68,500
Position: $1000
Previous: Closed LONG at +$23.50 (+2.35%)
───────────────
⏳ Entry pending on next candle open
```

### Hourly Statistics
```
📊 Stats Summary (Last 1h)
Symbol: BTCUSDT | Timeframe: 5m
───────────────
Gap Count: 8
├─ BULLISH: 5
└─ BEARISH: 3
───────────────
Performance:
├─ Total Trades: 12
├─ Wins: 8 (66.7%)
├─ Losses: 4 (33.3%)
├─ Avg Win: +$18.50 (+1.85%)
├─ Avg Loss: -$8.25 (-0.83%)
├─ Cumulative P&L: +$124.00
├─ Total Fees: $7.20
└─ Net P&L: +$116.80
───────────────
Runtime: 3h 24m
Volume Traded: $12,000
```

## CSV Output Format

### Gaps CSV
```csv
detected_at_utc,symbol,polarity,gap_level,gap_opening_bar_time,detection_bar_time,sequence
2025-11-16T16:15:23.456789+00:00,BTCUSDT,bullish,67250.00,2025-11-16T14:35:00+00:00,2025-11-16T16:15:00+00:00,1
2025-11-16T19:45:12.789012+00:00,BTCUSDT,bearish,68500.00,2025-11-16T18:20:00+00:00,2025-11-16T19:45:00+00:00,1
```

### Trades CSV
```csv
Status,Open Time,Close Time,Market,Side,Entry Price,Exit Price,Position Size ($),Position Size (Qty),Gross P&L,Realized P&L,Total Fees,Close Reason,Cumulative Wins,Cumulative Losses,Cumulative P&L,Cumulative Fees
WIN,2025-11-16T16:20:00+00:00,2025-11-16T19:50:00+00:00,BTCUSDT,LONG,67300.00,68500.00,1000.00,0.014859,17.85,17.25,0.60,REVERSE,1,0,17.25,0.60
LOSS,2025-11-16T19:50:00+00:00,2025-11-16T22:15:00+00:00,BTCUSDT,SHORT,68500.00,69200.00,1000.00,0.014599,-10.22,-10.82,0.60,REVERSE,1,1,6.43,1.20
```

## Command-Line Options

### V3 Detector Options
```bash
python3 binance_extgap_detector_v3_pinescript.py --help
```

| Option | Default | Description |
|--------|---------|-------------|
| `--symbol` | BTCUSDT | Trading symbol (BTCUSDT, ETHUSDT, etc.) |
| `--timeframe` | 1m | Candle interval (1m, 3m, 5m, 15m, 1h, etc.) |
| `--stats-interval` | 1h | Stats reporting interval (10m, 30m, 1h, 2h, 4h, 24h) |
| `--notional` | 1000 | Position size in USD |
| `--entry-fee-rate` | 0.0003 | Entry fee rate (3 bps) |
| `--exit-fee-rate` | 0.0003 | Exit fee rate (3 bps) |
| `--log-level` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `--no-telegram` | False | Disable Telegram notifications |

### Trading Bot Options

Same as V3 detector, plus:
| Option | Default | Description |
|--------|---------|-------------|
| `--instance` | LOCAL | Instance identifier for multi-deployment |
| `--max-positions` | 1 | Maximum concurrent positions per symbol |

## Development

### Adding New Timeframes

```bash
# Copy existing script
cp binance_extgap_indicator_2m.py binance_extgap_indicator_15m.py

# Update default timeframe (line ~1146)
parser.add_argument("--timeframe", default="15m", ...)

# Update output paths (lines ~1153, 1160)
parser.add_argument("--output", default="data/binance_extgap_15m_gaps.csv", ...)

# Update Telegram token fallback (lines ~681-686)
bot_token = os.getenv("TELEGRAM_BOT_TOKEN_EXTGAP_15M") or ...

# Add .env credentials
echo "TELEGRAM_BOT_TOKEN_EXTGAP_15M=your_token" >> .env

# Test
./start_extgap_indicator.sh --timeframe 15m --bg
```

### Modifying Gap Detection Logic

Edit `ExternalGapSymbolState.add_candle()` method:

```python
# File: binance_extgap_detector_v3_pinescript.py
# Lines: ~200-350

def add_candle(self, candle: Candle) -> Optional[ExternalGapDetection]:
    # Add your custom logic here
    # Modify candidate calculation
    # Change gap detection conditions
    ...
```

### Customizing Trade Strategy

Edit `ExtGapTradeManager` methods:

```python
# File: binance_extgap_indicator_2m.py
# Lines: ~373-554

def open_or_reverse(self, ...):
    # Modify position sizing
    # Add custom entry/exit conditions
    # Change fee calculations
    ...
```

## Troubleshooting

### No Gaps Detected

**This is normal!** External gaps require specific market conditions:
- Clear trend direction
- Sufficient volatility
- Price breaking beyond candidate extremes

**To increase gap frequency:**
- Try volatile symbols: SOLUSDT, ETHUSDT, BNBUSDT
- Use shorter timeframes: 1m, 2m, 3m
- Monitor during high-volatility periods (news events, market opens)

See [TROUBLESHOOTING_NO_GAPS.md](TROUBLESHOOTING_NO_GAPS.md) for detailed analysis.

### WebSocket Disconnections

The bot auto-reconnects with exponential backoff (1s → 60s max). Check logs:
```bash
grep "WebSocket\|Reconnecting" logs/extgap_v3_btcusdt_5m.log | tail -20
```

If persistent:
```bash
# Check network
ping fstream.binance.com

# Verify API accessible
curl https://fapi.binance.com/fapi/v1/ping

# Check for rate limiting
grep "429\|rate limit" logs/extgap_v3_btcusdt_5m.log
```

### No Telegram Notifications

```bash
# Verify credentials loaded
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
print('Token:', os.getenv('TELEGRAM_BOT_TOKEN_EXTGAP_DETECTOR'))
print('Chat IDs:', os.getenv('TELEGRAM_CHAT_IDS_EXTGAP_DETECTOR'))
"

# Test bot token
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe

# Check logs
grep -i "telegram\|notification" logs/extgap_v3_btcusdt_5m.log | tail -20
```

### Bot Won't Start - PID File Exists

```bash
# Check if actually running
ps -p $(cat binance_extgap_detector_v3.pid) 2>/dev/null

# If not running, remove stale PID
rm -f binance_extgap_detector_v3.pid

# Restart
python3 binance_extgap_detector_v3_pinescript.py
```

## Performance Characteristics

- **CPU Usage**: ~1-2% (single symbol)
- **Memory Usage**: ~50-80MB (500 candle history)
- **WebSocket Latency**: <100ms typical
- **Gap Detection**: O(1) per candle (V3: O(n) group operations where n ≤ 500)
- **CSV Writes**: Append-only, negligible overhead
- **Telegram API**: Async, non-blocking

## Security Notes

- ✅ **Read-only data** - No Binance API keys needed
- ✅ **Simulated trading** - No real funds at risk (detector scripts)
- ⚠️ **Telegram tokens** - Keep `.env` file secure, never commit
- ⚠️ **Log files** - May contain chat IDs and instance info
- ✅ **PID files** - Prevent duplicate instances
- ✅ **`.gitignore`** - Excludes `.env`, `data/`, `logs/`, `__pycache__/`

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Step-by-step startup guide
- **[CLAUDE.md](CLAUDE.md)** - Complete architecture documentation
- **[TESTING_V3.md](TESTING_V3.md)** - V3 testing and validation guide
- **[TROUBLESHOOTING_NO_GAPS.md](TROUBLESHOOTING_NO_GAPS.md)** - Gap detection troubleshooting
- **[COMMANDS.txt](COMMANDS.txt)** - Complete command reference

## License

MIT License - see LICENSE file for details

## Acknowledgments

- Inspired by TradingView "[THE] eG v2" PineScript indicator
- Uses Binance Futures WebSocket API for real-time data
- Built with Python asyncio for high-performance streaming

## Support

- 🐛 **Issues**: [GitHub Issues](https://github.com/PeterK1810/binance-extgap-detector/issues)
- 📧 **Email**: [Create an issue for support]
- 💬 **Discussions**: [GitHub Discussions](https://github.com/PeterK1810/binance-extgap-detector/discussions)

---

**⚠️ Disclaimer**: This software is for educational and research purposes only. Simulated trades do not represent actual trading results. Cryptocurrency trading involves substantial risk. Always perform your own research and risk assessment before trading real funds.
