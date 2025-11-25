# Testing Guide for External Gap Detector V3

## Quick Start

### Running the Script

```bash
# Activate virtual environment
source ../venv/bin/activate

# Run the detector (interactive mode)
python3 binance_extgap_detector_v3_pinescript.py
```

### Interactive Configuration Example

```
======================================================================
  Binance External Gap Detector v3 - Configuration
  PineScript '[THE] eG v2' Algorithm
======================================================================

📊 SYMBOL
   Available: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, etc.
   Enter symbol [BTCUSDT]: ETHUSDT

⏰ TIMEFRAME
   Available: 1m, 2m, 3m, 5m, 15m, 30m, 1h, 4h, 1d
   Enter timeframe [2m]: 5m

📈 STATISTICS NOTIFICATION INTERVAL
   Examples: 10m, 30m, 1h, 2h, 4h, 6h, 12h, 1d
   Enter interval [1h]: 30m

======================================================================
  CONFIGURATION SUMMARY
======================================================================
  Symbol:          ETHUSDT
  Timeframe:       5m (5 minutes)
  Stats interval:  30m (30 minutes)
======================================================================

Proceed with these settings? [Y/n]: y
```

---

## Test Checklist

### ✅ 1. Interactive Configuration

- [ ] Symbol prompt accepts custom input (e.g., ETHUSDT, SOLUSDT)
- [ ] Symbol prompt uses default BTCUSDT when Enter pressed
- [ ] Timeframe prompt accepts various formats (1m, 2m, 5m, 15m, 1h, 4h)
- [ ] Stats interval accepts all valid formats (10m, 30m, 1h, 2h, 4h, 1d)
- [ ] Invalid interval format shows error and exits
- [ ] Configuration summary shows correct values
- [ ] Typing 'n' at confirmation exits script cleanly

**Test commands:**
```bash
# Test default values (just press Enter 3 times)
python3 binance_extgap_detector_v3_pinescript.py

# Test custom values
# Input: ETHUSDT, 5m, 30m
python3 binance_extgap_detector_v3_pinescript.py

# Test invalid interval (should show error)
# Input: BTCUSDT, 2m, 45x (invalid format)
python3 binance_extgap_detector_v3_pinescript.py
```

---

### ✅ 2. Candle Synchronization

- [ ] Script waits for first aligned candle after WebSocket connects
- [ ] Logs show "Skipping misaligned candle" for non-aligned candles
- [ ] Logs show "✅ First aligned candle received" when aligned candle arrives
- [ ] Runtime validation detects misaligned candles (logs errors)
- [ ] Missing candles are detected and logged with warning
- [ ] After reconnection, script waits for aligned candle again

**Expected log output:**
```
2025-11-14 10:37:12 | INFO     | Connecting to Binance WebSocket: wss://fstream.binance.com/ws/btcusdt@kline_2m
2025-11-14 10:37:13 | INFO     | ✅ WebSocket connected
2025-11-14 10:37:45 | WARNING  | ⚠️ Skipping misaligned candle: 2025-11-14 10:37:00+00:00 (waiting for 2m boundary)
2025-11-14 10:38:02 | INFO     | ✅ First aligned candle received: 2025-11-14 10:38:00+00:00
2025-11-14 10:38:02 | INFO     | Closed candle: 2025-11-14 10:38:00+00:00 | O:103450.20 H:103480.50 L:103420.10 C:103445.80
```

**Test scenarios:**
1. Start bot at :37 seconds → should skip candles until :38:00 or :40:00
2. Start bot at exact boundary (e.g., 10:40:00) → processes immediately
3. Manually kill WebSocket connection (Ctrl+Z) → should reconnect and re-align

---

### ✅ 3. Group-Based Gap Detection

- [ ] First gap is detected using group extremes (max low / min high)
- [ ] First gap initializes candidates from bars AFTER gap opening bar
- [ ] Subsequent gaps detected when price breaks candidates
- [ ] Group cleanup removes bars ≤ gap opening bar
- [ ] Candidates recalculated from remaining group bars
- [ ] Empty group after cleanup uses current candle for candidates

**Expected log output:**
```
2025-11-14 10:52:00 | INFO     | 🚨 GAP DETECTED: BULLISH #1 at 103459.50 | First:True Reversal:False GroupSize:0
2025-11-14 11:18:00 | INFO     | 🚨 GAP DETECTED: BULLISH #2 at 104120.80 | First:False Reversal:False GroupSize:13
2025-11-14 12:04:00 | INFO     | 🚨 GAP DETECTED: BEARISH #1 at 103200.00 | First:False Reversal:True GroupSize:23
```

**Validation:**
- Check CSV file shows `group_size_before_cleanup` column
- Verify group size increases between same-polarity gaps
- Verify group size resets after cleanup

---

### ✅ 4. Sequence Numbering

- [ ] First gap shows sequence #1
- [ ] Same polarity gaps increment: #1, #2, #3, #4...
- [ ] Reversal resets to #1
- [ ] Telegram messages show correct sequence numbers
- [ ] Stats message shows current sequence

**Expected behavior:**
```
Bullish #1 → Bullish #2 → Bullish #3 → Bearish #1 → Bearish #2 → Bullish #1
```

**CSV validation:**
```csv
detected_at_utc,symbol,polarity,gap_level,gap_opening_bar_time,detection_bar_time,is_first_gap,is_reversal,sequence_number,group_size_before_cleanup
2025-11-14T10:52:00,BTCUSDT,bullish,103459.50,2025-11-14T10:35:00,2025-11-14T10:52:00,True,False,1,0
2025-11-14T11:18:00,BTCUSDT,bullish,104120.80,2025-11-14T11:10:00,2025-11-14T11:18:00,False,False,2,13
2025-11-14T12:04:00,BTCUSDT,bearish,103200.00,2025-11-14T11:58:00,2025-11-14T12:04:00,False,True,1,23
```

---

### ✅ 5. Telegram Notifications

**Prerequisites:**
- Ensure `.env` file in parent directory contains:
  ```bash
  TELEGRAM_BOT_TOKEN_EXTGAP_DETECTOR=your_token
  TELEGRAM_CHAT_IDS_EXTGAP_DETECTOR=chat_id1,chat_id2
  ```

**Test cases:**

- [ ] **Startup notification**
  ```
  🚀 BOT V3 DÉMARRÉ - BTCUSDT
  ━━━━━━━━━━━━━━━━━━━━
  ⏰ 10:30:00 UTC
  📊 Version: V3 (PineScript Algorithm)
  ⏱️ Timeframe: 2m
  📈 Stats interval: 1h
  🔍 Statut: Surveillance active
  ━━━━━━━━━━━━━━━━━━━━
  ✅ Détection des gaps externes en cours...
  ```

- [ ] **First gap notification**
  ```
  🚀 PREMIER GAP DÉTECTÉ - BTCUSDT
  ━━━━━━━━━━━━━━━━━━━━
  ⏰ 10:52:00 UTC
  📊 Polarité: BULLISH #1 ⬆️
  💰 Niveau: 103,459.50 USDT
  🕒 Barre ouverture: 10:35:00
  ━━━━━━━━━━━━━━━━━━━━
  ⚠️ Pas de trade - attente inversion
  ```

- [ ] **Normal gap (same polarity)**
  ```
  📊 GAP BULLISH #3 DÉTECTÉ - BTCUSDT
  ━━━━━━━━━━━━━━━━━━━━
  ⏰ 11:18:00 UTC
  💰 Niveau: 104,120.80 USDT
  📈 Séquence: BULLISH #3
  ━━━━━━━━━━━━━━━━━━━━
  ```

- [ ] **Reversal notification**
  ```
  🔄 INVERSION DE TENDANCE - BTCUSDT
  ━━━━━━━━━━━━━━━━━━━━
  ⏰ 12:04:00 UTC
  🟢 BULLISH #5 → 🔴 BEARISH #1
  💰 Nouveau niveau: 103,200.00 USDT
  📊 Gap précédent: 104,120.80 (bullish #5)
  ━━━━━━━━━━━━━━━━━━━━
  ✅ Signal potentiel d'entrée
  ```

- [ ] **Stats notification (at configured interval)**
  ```
  📊 STATISTIQUES (30min) - BTCUSDT
  ━━━━━━━━━━━━━━━━━━━━
  🕐 15:30 UTC
  ⏱️ Timeframe: 2m
  ⬆️ Gaps bullish: 12
  ⬇️ Gaps bearish: 8
  🔄 Inversions: 4
  ⏱️ Fréquence moyenne: 35.2 min
  💡 Tendance actuelle: 🟢 BULLISH #3
  ━━━━━━━━━━━━━━━━━━━━
  ```

---

### ✅ 6. Dynamic Output Paths

- [ ] CSV file created: `data/extgap_v3_{symbol}_{timeframe}_gaps.csv`
- [ ] Log file created: `logs/extgap_v3_{symbol}_{timeframe}.log`
- [ ] Directories created automatically if don't exist
- [ ] Multiple instances with different symbols don't conflict

**Examples:**
```
data/extgap_v3_btcusdt_2m_gaps.csv
data/extgap_v3_ethusdt_5m_gaps.csv
data/extgap_v3_solusdt_15m_gaps.csv

logs/extgap_v3_btcusdt_2m.log
logs/extgap_v3_ethusdt_5m.log
```

---

### ✅ 7. Stats Interval Flexibility

Test various intervals:
- [ ] **10m**: Stats sent every 10 minutes
- [ ] **30m**: Stats sent every 30 minutes
- [ ] **1h**: Stats sent every hour
- [ ] **2h**: Stats sent every 2 hours
- [ ] **4h**: Stats sent every 4 hours

**Validation:**
- Check Telegram message timestamps
- Verify interval matches configured value
- Ensure stats don't send before interval elapsed

---

### ✅ 8. Edge Cases

- [ ] **Bot started mid-gap formation**: Should detect next gap correctly
- [ ] **High volatility (many gaps)**: System handles rapid gap detection
- [ ] **Low volatility (no gaps)**: System runs without errors, no false positives
- [ ] **Network interruption**: Auto-reconnects, resumes detection
- [ ] **Malformed WebSocket data**: Logs error, continues processing
- [ ] **Ctrl+C shutdown**: Clean exit with shutdown message

---

## Performance Benchmarks

### Expected Resource Usage

| Metric | Expected Value |
|--------|----------------|
| CPU Usage | 1-3% (single core) |
| Memory | 50-100 MB |
| WebSocket Latency | <100ms |
| CSV Write Time | <1ms per gap |
| Telegram Send Time | 100-500ms |

### Monitor Performance

```bash
# CPU and memory usage
top -p $(pgrep -f binance_extgap_detector_v3)

# Network connections
netstat -an | grep 9443  # Binance WebSocket port

# File sizes
ls -lh data/extgap_v3_*.csv
ls -lh logs/extgap_v3_*.log
```

---

## Comparison with V1/V2

### Run All Three Versions Simultaneously

```bash
# Terminal 1: V1 (simple reset)
./start_extgap_detector.sh --version v1 --bg

# Terminal 2: V2 (corrected reset)
./start_extgap_detector.sh --version v2 --bg

# Terminal 3: V3 (PineScript algorithm) - interactive
python3 binance_extgap_detector_v3_pinescript.py
# Input: BTCUSDT, 2m, 1h
```

### Compare Results After 24 Hours

```bash
# Gap counts
echo "V1 gaps: $(wc -l < data/extgap_detector_v1_gaps.csv)"
echo "V2 gaps: $(wc -l < data/extgap_detector_v2_gaps.csv)"
echo "V3 gaps: $(wc -l < data/extgap_v3_btcusdt_2m_gaps.csv)"

# Gap timing comparison
diff data/extgap_detector_v1_gaps.csv data/extgap_v3_btcusdt_2m_gaps.csv

# Reversal counts
echo "V1 reversals: $(grep -c "True" data/extgap_detector_v1_gaps.csv)"
echo "V2 reversals: $(grep -c "True" data/extgap_detector_v2_gaps.csv)"
echo "V3 reversals: $(grep -c "True" data/extgap_v3_btcusdt_2m_gaps.csv)"
```

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'websockets'"

**Solution:**
```bash
source ../venv/bin/activate
pip install websockets aiohttp python-dotenv
```

### Issue: No Telegram notifications

**Solution:**
1. Check `.env` file exists in parent directory
2. Verify credentials:
   ```bash
   python3 -c "import os; from dotenv import load_dotenv; load_dotenv('../.env'); print(os.getenv('TELEGRAM_BOT_TOKEN_EXTGAP_DETECTOR'))"
   ```
3. Test bot token manually:
   ```bash
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
   ```

### Issue: Script doesn't wait for aligned candle

**Solution:**
- Check logs for "✅ First aligned candle received" message
- Verify timeframe is valid Binance interval (1m, 2m, 3m, 5m, 15m, 30m, 1h, 4h, 1d)
- Ensure system clock is synchronized

### Issue: Gaps not detected

**Solution:**
- This is normal! External gaps require specific market conditions
- Try:
  - More volatile symbols (SOLUSDT, BNBUSDT)
  - Shorter timeframes (1m, 2m)
  - Wait longer (gaps may be infrequent on stable coins)

---

## Success Criteria

✅ **All tests passed if:**

1. Script runs without errors for 1+ hour
2. At least 1 gap detected and recorded to CSV
3. Telegram notifications sent for all gap types
4. Candle synchronization logs show proper alignment
5. Sequence numbers increment correctly
6. Stats notification sent at configured interval
7. CSV file contains all required fields
8. Log file shows no CRITICAL or ERROR messages (except network reconnects)

---

## Contact & Support

For issues or questions:
1. Check logs: `tail -f logs/extgap_v3_*.log`
2. Verify CSV data: `tail -20 data/extgap_v3_*.csv`
3. Review CLAUDE.md for architecture details
4. Compare behavior with v1/v2 implementations
