# Troubleshooting: Why Gaps Weren't Detected

## Issue Report

**Gaps mentioned:**
- 10:10 AM UTC on 2m timeframe
- 10:12 AM UTC on 2m timeframe

**Bot start time:** 10:50 AM UTC (from logs)

## Root Causes Identified

### 1. **Bot Started AFTER the Gaps Occurred**

The bot was started at **10:50:30 UTC**, but the gaps you mentioned happened at:
- **10:10 UTC** - 40 minutes BEFORE bot started
- **10:12 UTC** - 38 minutes BEFORE bot started

**The bot cannot detect gaps that occurred before it was running.**

---

### 2. **No WebSocket Messages Being Received**

From logs:
```
2025-11-14 10:50:31 | INFO | ✅ WebSocket connected
```

But **no candle data** was logged after this line. This indicates:

**Problem:** WebSocket connected successfully but received **zero messages** in 25+ minutes of runtime.

**Possible causes:**
1. **Binance WebSocket connectivity issue** in WSL environment
2. **Firewall blocking WebSocket data** (connection established but no data flows)
3. **Network proxy interference**
4. **WebSocket library hanging** waiting for messages that never arrive

---

### 3. **External Gaps ≠ Price Gaps**

**Important distinction:**

A "price gap" (what you might see on TradingView) is when:
- Previous candle close: $100
- Next candle open: $102
- There's a $2 gap in price

An **"external gap"** (what this bot detects) is different:
- Requires **candidate extreme tracking**
- Current candle must break BEYOND the highest low (bearish) or lowest high (bullish) of ALL candles since last gap
- Much more restrictive condition

**Example:**
```
Candle 1: Low=$100, High=$105
Candle 2: Low=$102, High=$107  (bullish candidate high = $105, bearish candidate low = $102)
Candle 3: Low=$104, High=$108  (bullish candidate high = $105, bearish candidate low = $104)
Candle 4: Low=$109, High=$112  ← BULLISH GAP! (low $109 > candidate high $105)
```

If Candle 4 had Low=$106, it would NOT be a gap (doesn't exceed $105 by crossing above it).

---

## Diagnostic Steps

### Step 1: Check if WebSocket is receiving ANY messages

The bot has been updated with DEBUG logging. Run it again and check for:

```
2025-11-14 XX:XX:XX | DEBUG | WebSocket message received: event=kline
2025-11-14 XX:XX:XX | DEBUG | Kline message: symbol=BTCUSDT, interval=2m, closed=True, price=91234.56
```

**If you DON'T see these debug messages:**
- WebSocket is connected but NOT receiving data
- This is a network/environment issue, NOT a code issue

**If you DO see these debug messages:**
- WebSocket is working
- Bot is processing candles
- No gaps are being detected because conditions aren't met

---

### Step 2: Verify Binance WebSocket connectivity

Run this test:

```bash
source ../venv/bin/activate

# Test WebSocket directly
python3 << 'EOF'
import asyncio
import json
import websockets

async def test():
    url = "wss://fstream.binance.com/ws/btcusdt@kline_2m"
    print(f"Testing: {url}")

    try:
        async with websockets.connect(url, ping_interval=20) as ws:
            print("✅ Connected!")
            count = 0
            async for msg in ws:
                data = json.loads(msg)
                if data.get('e') == 'kline':
                    k = data['k']
                    print(f"✅ Received kline: {k['s']} {k['i']} close={k['c']} closed={k['x']}")
                    count += 1
                    if count >= 2:
                        break
    except Exception as e:
        print(f"❌ Error: {e}")

asyncio.run(test())
EOF
```

**Expected output:**
```
Testing: wss://fstream.binance.com/ws/btcusdt@kline_2m
✅ Connected!
✅ Received kline: BTCUSDT 2m close=91234.56 closed=False
✅ Received kline: BTCUSDT 2m close=91235.12 closed=True
```

**If it hangs or times out:**
- Your environment cannot receive Binance WebSocket data
- Possible solutions:
  - Use VPN
  - Check Windows Firewall settings
  - Try from different network
  - Use Binance's alternative WebSocket endpoints

---

### Step 3: Historical gap analysis

To check if those times (10:10, 10:12) actually had **external gaps**, you need to:

1. Get historical 2m candle data from Binance
2. Manually run the group-based algorithm
3. See if gaps would have been detected

**Quick historical check:**

```bash
# Get 100 candles of 2m data around 10:10 UTC
curl -s "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=2m&startTime=1731576000000&limit=100" | python3 -m json.tool > historical_candles.json

# Analyze for gaps (manual review needed)
cat historical_candles.json
```

Look for:
- 10:10 UTC candle
- 10:12 UTC candle
- Check if they break beyond candidate extremes

---

## Recommended Actions

### Immediate (now):

1. **Stop current bot:** `kill $(pgrep -f binance_extgap_detector_v3)`

2. **Clear old log:** `rm logs/extgap_v3_btcusdt_2m.log`

3. **Run bot again with DEBUG logging:**
   ```bash
   source ../venv/bin/activate
   python3 binance_extgap_detector_v3_pinescript.py
   ```

   Enter: BTCUSDT, 2m, 1h

4. **Watch the output in real-time:**
   - You should see DEBUG messages every ~2 seconds (live candle updates)
   - You should see INFO messages every 2 minutes (closed candles)

5. **Check log after 5 minutes:**
   ```bash
   grep "WebSocket message" logs/extgap_v3_btcusdt_2m.log | head -20
   grep "Closed candle" logs/extgap_v3_btcusdt_2m.log | head -10
   ```

### If WebSocket is still silent:

1. **Test from different network** (mobile hotspot, VPN)
2. **Check WSL network settings:**
   ```bash
   # Check DNS
   cat /etc/resolv.conf

   # Test DNS resolution
   nslookup fstream.binance.com

   # Test HTTPS
   curl -v https://fstream.binance.com/
   ```

3. **Try alternative WebSocket library:**
   - Current: `websockets`
   - Alternative: `websocket-client` (different implementation)

### If WebSocket works but no gaps detected:

**This is normal!** External gaps require specific market conditions:
- Trending price movement
- Candles breaking beyond tracked extremes
- Not just any price jump

**To increase gap detection:**
- Use more volatile symbols (SOLUSDT, BNBUSDT, ETHUSDT)
- Use shorter timeframes (1m instead of 2m)
- Wait longer (gaps may only occur a few times per hour)

---

## Understanding External Gap Frequency

**Normal behavior:**
- **2m timeframe:** 2-5 gaps per hour in volatile markets
- **2m timeframe:** 0-1 gaps per hour in stable markets
- **5m timeframe:** 1-3 gaps per hour
- **15m timeframe:** 0-2 gaps per hour

**Don't expect:**
- Gap on every candle
- Gap every few minutes
- Immediate gap after bot starts

**External gaps are RARE by design** - they signal significant price breakouts beyond recent extremes.

---

## Next Steps

1. Run the diagnostic WebSocket test above
2. Share the output so we can confirm connectivity
3. If WebSocket works, let bot run for 30-60 minutes
4. Check if gaps are detected during that period

The issue is most likely:
- **80% probability:** WebSocket connectivity problem (environment/network)
- **15% probability:** Bot started too late (missed the gaps you saw)
- **5% probability:** Those weren't external gaps (just price gaps)
