# External Gap Indicator - Quick Start Guide

## Prerequisites

✅ Telegram credentials already configured in `../.env`:
- `TELEGRAM_BOT_TOKEN_EXTGAP_5M=8146581274:AAH9AzQzhttftcaiJbrnyRkUY4z2ZOpQJd0`
- `TELEGRAM_CHAT_IDS_EXTGAP_5M=1474566688,-1002985538408`

## Start the Indicator

### Option 1: Using Shell Script (Recommended)

```bash
# Start in background
./start_extgap_indicator.sh --bg

# Start in foreground (for testing)
./start_extgap_indicator.sh
```

### Option 2: Direct Python Command

```bash
# With default settings (BTCUSDT, 5m)
python binance_extgap_indicator_5m.py

# With custom settings
python binance_extgap_indicator_5m.py \
  --symbol ETHUSDT \
  --timeframe 5m \
  --notional 2000 \
  --log-level DEBUG
```

## What to Expect

### 1. Startup
You'll receive a Telegram message:
```
🚀 External Gap Indicator Started
Instance: LOCAL
Strategy: Trend-following with position reversal
Exit logic: Reverse on opposite gap signal
```

### 2. First Gap Detection (No Trade)
When the first gap is detected, you'll see:
```
🔵 BULLISH External Gap Detected
Symbol: BTCUSDT
Gap Level: $67250.00
───────────────
📊 Gap Formation:
Candidate set: 2025-11-11 14:35 UTC
Gap detected: 2025-11-11 16:15 UTC
Duration: 1h 40m
───────────────
⏳ Waiting for reversal to start trading
```

**Note:** No trade is opened yet. The bot is waiting for a reversal (opposite polarity gap).

### 3. First Reversal (Trade Entry)
When an opposite gap appears:
```
🔴 BEARISH External Gap Detected
Symbol: BTCUSDT
Gap Level: $68500.00
───────────────
📊 Gap Formation:
Candidate set: 2025-11-11 18:20 UTC
Gap detected: 2025-11-11 19:45 UTC
Duration: 1h 25m
───────────────
⏳ Entry pending on next candle open
```

Then on the next candle open:
```
📉 SHORT Entry Executed
Symbol: BTCUSDT
Entry Time: 2025-11-11 19:50 UTC
───────────────
Entry Price: $68520.00
Gap Level: $68500.00
Distance: $20.00 (0.03%)
───────────────
Position Size: $1000.00
Qty: 0.014593
Entry Fee: $0.20
───────────────
Exit: Reverse on opposite gap signal
```

### 4. Subsequent Reversals
Each opposite gap will:
1. Close the current position
2. Open a new position in the opposite direction
3. Send trade close and trade open notifications

## Monitoring

### Check Status
```bash
./status_extgap_indicator.sh
```

### View Logs
```bash
# Live logs
tail -f logs/extgap_indicator_5m.log

# Recent errors only
tail -f logs/extgap_indicator_5m.log | grep ERROR
```

### View Data Files
```bash
# Gap detections
cat data/binance_extgap_5m_gaps.csv

# Trade results
cat data/binance_extgap_5m_trades.csv
```

## Stop the Indicator

```bash
./stop_extgap_indicator.sh
```

You'll receive a Telegram message:
```
🛑 External Gap Indicator Stopped
Instance: LOCAL
Reason: User interrupt
```

## Key Behavior Points

### ⚠️ First-Reversal Strategy
- **First gap detected**: No trade (waiting for reversal)
- **Same polarity gaps**: Still no trade (still waiting)
- **Opposite polarity gap**: First trade entry!
- **After first trade**: Every reversal closes and opens opposite position

### ⚠️ No Historical Data
- Bot only detects gaps going forward (real-time only)
- No backfilling of historical candles
- Clean start - no pre-existing gaps

### ⚠️ No Stop Loss or Take Profit
- Positions remain open until opposite gap appears
- Pure trend-following approach
- Can hold positions for hours or days

## Example Scenario

```
Time    Event                           Action
------  ------                          ------
10:00   Bot starts                      Monitoring...
10:05   Bullish gap @ $67,000          First gap - NO TRADE
10:10   Another bullish gap @ $67,500   Same polarity - NO TRADE
10:15   Bearish gap @ $68,000          REVERSAL! → SHORT entry @ next open
10:20   Next candle opens @ $68,050     Short position opened
12:30   Bullish gap @ $67,200          REVERSAL! → Close SHORT, open LONG
12:35   Next candle opens @ $67,250     Long position opened, short closed
15:00   Bearish gap @ $68,800          REVERSAL! → Close LONG, open SHORT
...
```

## Troubleshooting

### No Telegram messages
1. Check `.env` file has correct credentials
2. Verify bot token with `@BotFather` on Telegram
3. Check logs: `tail -f logs/extgap_indicator_5m.log`

### Bot won't start
1. Check if already running: `./status_extgap_indicator.sh`
2. Remove stale PID: `rm binance_extgap_indicator_5m.pid`
3. Check logs for errors

### No gaps detected
- This is normal! External gaps may take time to form
- Check Binance directly to see if price is trending
- Try a different symbol with more volatility

## Performance Tips

- Start with BTCUSDT (most liquid)
- Use 5m timeframe (good balance of frequency)
- Default $1000 notional is safe for testing
- Monitor first few trades before increasing size

## Next Steps

1. **Test with small position size** ($100-1000)
2. **Monitor for 24-48 hours** to see gap frequency
3. **Analyze CSV data** to review performance
4. **Adjust symbol** if not enough gaps (try ETHUSDT, SOLUSDT)
5. **Scale up** once comfortable with the strategy

---

**Ready to start?**

```bash
./start_extgap_indicator.sh --bg
```

🚀 Happy trading!
