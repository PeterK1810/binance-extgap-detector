# Multi-Timeframe Bot Deployment - Implementation Progress

**Last Updated:** 2025-11-25 14:50 UTC
**Status:** 🚧 IN PROGRESS - 4-Timeframe Upgrade (3m, 5m, 15m, 1h)
**Environment:** Replit
**Target Timeframes:** 3m, 5m, 15m, 1h (adding 5m, upgrading to French notifications)

---

## 🔄 CURRENT SESSION - 4-Timeframe Upgrade (2025-11-25)

### Session Goal
Upgrade from 3-timeframe (3m, 15m, 1h) to 4-timeframe (3m, 5m, 15m, 1h) deployment with:
- French-format Telegram notifications (matching README.md template)
- Sequence number tracking (#1, #2, #3) for all bots
- Per-timeframe stats intervals (3m=30m, 5m=1h, 15m=2h, 1h=4h)
- Fixed default timeframe arguments
- Supervisord configuration for all 4 bots

### Implementation Progress

#### ✅ Phase 1: Cleanup and Preparation (COMPLETED)
**Timestamp:** 2025-11-25 14:48 UTC

**Actions Taken:**
1. Created `archive/` directory
2. Moved `binance_extgap_indicator_2m.py` to `archive/binance_extgap_indicator_2m.py`
   - Reason: 2m bot not part of 4-timeframe requirement
   - Kept for reference (has working French notifications)
3. Fixed broken symlink `binance_extgap_indicator_1m.py`
   - Old: Pointed to non-existent `binance_extgap_indicator.py`
   - New: Points to `binance_extgap_indicator_3m.py`
4. Verified `.env` has all 4 Telegram tokens:
   - ✅ `TELEGRAM_BOT_TOKEN_EXTGAP_3M` (value: 8586866654:...)
   - ✅ `TELEGRAM_BOT_TOKEN_EXTGAP_5M` (value: 8204135201:...)
   - ✅ `TELEGRAM_BOT_TOKEN_EXTGAP_15M` (value: 8257546943:...)
   - ✅ `TELEGRAM_BOT_TOKEN_EXTGAP_1H` (value: 8146581274:...)

**Files Modified:**
- Created: `archive/` directory
- Moved: `binance_extgap_indicator_2m.py` → `archive/binance_extgap_indicator_2m.py`
- Modified: `binance_extgap_indicator_1m.py` symlink target

**Verification Commands:**
```bash
ls -lh archive/
ls -lh binance_extgap_indicator_1m.py  # Should show -> binance_extgap_indicator_3m.py
grep TELEGRAM_BOT_TOKEN_EXTGAP_ .env | grep -E "(3M|5M|15M|1H)"
```

#### ✅ Phase 2: Fix Default Timeframe Arguments (COMPLETED)
**Timestamp:** 2025-11-25 14:49 UTC

**Problem:** Bot files had incorrect default timeframe arguments causing silent failures.

**Files Modified:**
1. `binance_extgap_indicator_5m.py:1177`
   - Changed: `default="3m"` → `default="5m"`
   - Also updated help text: `"Kline interval (default: 3m)"` → `"Kline interval (default: 5m)"`

2. `binance_extgap_indicator_15m.py:1177`
   - Changed: `default="3m"` → `default="15m"`
   - Also updated help text: `"Kline interval (default: 3m)"` → `"Kline interval (default: 15m)"`

3. `binance_extgap_indicator_1h.py:1177`
   - Changed: `default="3m"` → `default="1h"`
   - Also updated help text: `"Kline interval (default: 3m)"` → `"Kline interval (default: 1h)"`

**Verification Commands:**
```bash
grep -A 2 '"--timeframe"' binance_extgap_indicator_5m.py | grep default
grep -A 2 '"--timeframe"' binance_extgap_indicator_15m.py | grep default
grep -A 2 '"--timeframe"' binance_extgap_indicator_1h.py | grep default
# Each should show their respective timeframe (5m, 15m, 1h)
```

#### ✅ Phase 3: Add Sequence Number Tracking (COMPLETED)
**Timestamp:** 2025-11-25 14:50 UTC

**Implementation:** Added full sequence tracking logic to all 4 bots using detector v1/v2 as reference.

**Changes Applied to Each Bot (3m, 5m, 15m, 1h):**

1. **ExternalGapDetection dataclass** (~line 91):
   - Added field: `sequence_number: int = 1  # Sequence number within current trend`

2. **ExternalGapSymbolState.__init__()** (~line 180-186):
   - Added: `self.current_sequence_number: int = 0`
   - Added: `self.last_sequence_number: int = 0  # Previous sequence before reversal`

3. **ExternalGapSymbolState.add_candle()** (~line 265-276):
   - Added sequence tracking logic BEFORE creating ExternalGapDetection:
   ```python
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
   ```

4. **ExternalGapDetection creation** (~line 278-287):
   - Added parameter: `sequence_number=self.current_sequence_number`

**Files Modified:**
- `binance_extgap_indicator_3m.py` (lines 91, 184-186, 265-287)
- `binance_extgap_indicator_5m.py` (lines 91, 184-186, 265-287)
- `binance_extgap_indicator_15m.py` (lines 91, 184-186, 265-287)
- `binance_extgap_indicator_1h.py` (lines 91, 184-186, 265-287)

**Verification Commands:**
```bash
# Check ExternalGapDetection dataclass has sequence_number field
grep -A 10 "class ExternalGapDetection" binance_extgap_indicator_3m.py | grep sequence_number

# Check ExternalGapSymbolState has tracking variables
grep -A 5 "# Sequence tracking" binance_extgap_indicator_3m.py

# Check detection logic includes sequence
grep -B 3 "self.current_sequence_number = 1" binance_extgap_indicator_3m.py
```

**Testing Plan for Phase 3:**
- Launch bot in foreground mode
- Wait for first gap → should show sequence #1
- Wait for second gap (same polarity) → should show sequence #2
- Wait for reversal gap → should reset to sequence #1

#### 🚧 Phase 4: Update Telegram Notification Format to French (PENDING)
**Status:** NOT STARTED
**Estimated Lines:** ~200 lines per bot (TelegramExtGapNotifier class)

**Plan:**
- Use archive/binance_extgap_indicator_2m.py as template (has working French format)
- Update TelegramExtGapNotifier class in all 4 bots (3m, 5m, 15m, 1h)
- Changes needed:
  1. Method signatures: Add sequence_number, prev_sequence, new_polarity parameters
  2. Message templates: Replace English with French, change `───` to `━━━`
  3. notify_startup(): French format
  4. notify_gap_detection(): Show sequence in title
  5. notify_trade_open(): Show sequence
  6. notify_trade_close(): Show reversal transition (e.g., "🔴 BEARISH #2 → 🟢 BULLISH #1")
  7. notify_hourly_stats(): Show current sequence
  8. Update method calls in main loop (~lines 1050-1065) to pass sequence numbers

**Files to Modify:**
- `binance_extgap_indicator_3m.py` (TelegramExtGapNotifier class ~lines 653-855)
- `binance_extgap_indicator_5m.py` (TelegramExtGapNotifier class ~lines 653-855)
- `binance_extgap_indicator_15m.py` (TelegramExtGapNotifier class ~lines 653-855)
- `binance_extgap_indicator_1h.py` (TelegramExtGapNotifier class ~lines 653-855)

#### 🚧 Phase 5: Update Stats Interval Per Timeframe (PENDING)
**Status:** NOT STARTED
**Estimated Lines:** 1 line per bot (default stats-interval argument)

**Plan:**
- Update default stats interval argument (~line 1156) in each bot:
  - 3m bot: `default="30m"`
  - 5m bot: `default="1h"`
  - 15m bot: `default="2h"`
  - 1h bot: `default="4h"`

**Files to Modify:**
- `binance_extgap_indicator_3m.py:~1156`
- `binance_extgap_indicator_5m.py:~1156`
- `binance_extgap_indicator_15m.py:~1156`
- `binance_extgap_indicator_1h.py:~1156`

#### 🚧 Phase 6: Update Supervisord Configuration (PENDING)
**Status:** NOT STARTED

**Plan:**
- Add 5m bot program definition to `supervisord.conf`
- Verify 3m, 15m, 1h programs have correct --stats-interval flags
- Update [group:extgap_bots] to include all 4: `programs=extgap_3m,extgap_5m,extgap_15m,extgap_1h`

**Files to Modify:**
- `supervisord.conf`

#### 🚧 Phase 7: Update start_all_bots.sh Script (PENDING)
**Status:** NOT STARTED

**Plan:**
- Add validation loop to check all 4 Telegram tokens before launching

**Files to Modify:**
- `start_all_bots.sh`

### Recovery Instructions

**If this session is interrupted, resume with:**

1. **Check Phase 3 completion:**
   ```bash
   grep "sequence_number: int = 1" binance_extgap_indicator_3m.py
   # Should return line with sequence_number field in ExternalGapDetection
   ```

2. **If Phase 3 complete, start Phase 4:**
   - Read `archive/binance_extgap_indicator_2m.py` for French notification template (lines 653-851)
   - Read `/home/runner/.claude/plans/tidy-munching-owl.md` for detailed Phase 4 plan
   - Start with `binance_extgap_indicator_3m.py` TelegramExtGapNotifier class

3. **Quick status check:**
   ```bash
   ls -lh archive/binance_extgap_indicator_2m.py  # Should exist
   grep 'default="5m"' binance_extgap_indicator_5m.py  # Should exist
   grep "self.current_sequence_number" binance_extgap_indicator_3m.py  # Should exist
   ```

### Rollback Commands (If Needed)

```bash
# Stop all bots
bash stop_all_bots.sh

# Restore 2m bot
mv archive/binance_extgap_indicator_2m.py .

# Revert changes
git checkout binance_extgap_indicator_*.py

# Restart old configuration
bash start_all_bots.sh
```

---

## 📊 PREVIOUS SESSION - 3-Timeframe Deployment (Historical)

---

## 📊 Implementation Status Summary

### ✅ Phase 1: Critical Bugs Fixed (COMPLETED)
- [x] Fixed 3M bot configuration bug - `binance_extgap_indicator_3m.py:686-692`
  - Changed from hardcoded 5M credentials to 3M-specific credentials
  - File: `/home/runner/workspace/binance_extgap_indicator_3m.py`
- [x] Added 3M Telegram credentials to `.env`
  - Token: `TELEGRAM_BOT_TOKEN_EXTGAP_3M` (reusing DETECTOR bot)
  - Chat IDs: `TELEGRAM_CHAT_IDS_EXTGAP_3M`
  - File: `/home/runner/workspace/.env`

### ✅ Phase 2: Supervisord Installed (COMPLETED)
- [x] Updated `replit.nix` with supervisor package
  - Added: `pkgs.python311Packages.supervisor`
  - File: `/home/runner/workspace/replit.nix`
- [x] Created supervisord configuration
  - Auto-restart on crash (infinite retries with exponential backoff)
  - Log rotation (10MB max, 3 backups per bot)
  - Graceful shutdown (30s timeout)
  - File: `/home/runner/workspace/supervisord.conf`

### ✅ Phase 3: Management Scripts Created (COMPLETED)
- [x] `start_all_bots.sh` - Master launcher script (executable)
- [x] `status_all_bots.sh` - Status checker (executable)
- [x] `stop_all_bots.sh` - Graceful shutdown (executable)
- [x] `restart_bot.sh` - Individual bot restart (executable)
- [x] All scripts made executable with `chmod +x`

### ✅ Phase 4: Replit Configuration Updated (COMPLETED)
- [x] Updated `.replit` file to launch supervisord
  - Run command: `["bash", "start_all_bots.sh"]`
  - Deployment configured
  - File: `/home/runner/workspace/.replit`

### ✅ Phase 5: Health Monitoring (COMPLETED)
- [x] Created `health_check.py` script (executable)
  - Checks all 3 bots via supervisord
  - Returns exit code 0 if healthy, 1 if any failures
  - File: `/home/runner/workspace/health_check.py`

---

## 📁 Files Modified

| File | Change | Status |
|------|--------|--------|
| `binance_extgap_indicator_3m.py` | Fixed 3M credentials bug (lines 686-692) | ✅ Done |
| `.env` | Added 3M Telegram tokens (after line 26) | ✅ Done |
| `replit.nix` | Added supervisor package | ✅ Done |
| `.replit` | Updated to launch supervisord | ✅ Done |

---

## 📁 Files Created

| File | Purpose | Status |
|------|---------|--------|
| `supervisord.conf` | Process manager configuration | ✅ Created |
| `start_all_bots.sh` | Master launcher | ✅ Created |
| `status_all_bots.sh` | Status checker | ✅ Created |
| `stop_all_bots.sh` | Graceful shutdown | ✅ Created |
| `restart_bot.sh` | Individual bot restart | ✅ Created |
| `health_check.py` | Health monitoring | ✅ Created |
| `PLAN.md` | This progress tracking document | ✅ Created |

---

## 🏗️ System Architecture

```
Replit Always-On ($20/mo)
    ↓
.replit file → bash start_all_bots.sh
    ↓
supervisord (process manager)
    ├── Bot 3M  → binance_extgap_indicator_3m.py
    │             → Telegram: DETECTOR (1474566688,-1003358731201)
    │
    ├── Bot 15M → binance_extgap_indicator_15m.py (symlink)
    │             → Telegram: 15M Channel (1474566688,-1003208418021)
    │
    └── Bot 1H  → binance_extgap_indicator_1h.py (symlink)
                  → Telegram: 1H Channel (1474566688,-1002985538408)
```

**Key Features:**
- Auto-restart on crash (10s delay, infinite retries)
- Log rotation (10MB × 4 files per bot = 40MB max per bot)
- Graceful shutdown (30s WebSocket cleanup timeout)
- Unified control (start/stop/status all bots)

---

## ✅ Testing Checklist

### ⏳ Phase 5: Individual Bot Testing (NOT STARTED)
- [ ] Test 3M bot in foreground mode
  ```bash
  python3 binance_extgap_indicator_3m.py --symbol BTCUSDT --timeframe 3m --log-level DEBUG
  ```
  - [ ] Telegram startup notification received (DETECTOR channel)
  - [ ] WebSocket connection established
  - [ ] Candles being processed
  - [ ] No Python exceptions

- [ ] Test 15M bot in foreground mode
  ```bash
  python3 binance_extgap_indicator_15m.py --symbol BTCUSDT --timeframe 15m --log-level DEBUG
  ```
  - [ ] Telegram startup notification received (15M channel)
  - [ ] WebSocket connection established
  - [ ] Candles being processed

- [ ] Test 1H bot in foreground mode
  ```bash
  python3 binance_extgap_indicator_1h.py --symbol BTCUSDT --timeframe 1h --log-level DEBUG
  ```
  - [ ] Telegram startup notification received (1H channel)
  - [ ] WebSocket connection established
  - [ ] Candles being processed

### ⏳ Phase 6: Supervisor Integration Testing (NOT STARTED)
- [ ] Launch all bots via supervisor
  ```bash
  bash start_all_bots.sh
  ```
  - [ ] All 3 bots show "RUNNING" status
  - [ ] Startup notifications received in all 3 Telegram channels
  - [ ] Supervisor logs clean (`tail -f logs/supervisord.log`)

- [ ] Check individual bot logs
  ```bash
  tail -f logs/extgap_indicator_3m_stdout.log
  tail -f logs/extgap_indicator_15m_stdout.log
  tail -f logs/extgap_indicator_1h_stdout.log
  ```
  - [ ] All bots processing candles
  - [ ] No errors in stderr logs

### ⏳ Phase 7: Crash Recovery Testing (NOT STARTED)
- [ ] Kill 3M bot process (simulate crash)
  ```bash
  ps aux | grep binance_extgap_indicator_3m
  kill -9 <PID>
  ```
  - [ ] Bot auto-restarts within 10 seconds
  - [ ] New startup notification sent to Telegram
  - [ ] Status shows "RUNNING" again

- [ ] Kill 15M bot and verify auto-restart
- [ ] Kill 1H bot and verify auto-restart

### ⏳ Phase 8: Graceful Shutdown Testing (NOT STARTED)
- [ ] Stop all bots gracefully
  ```bash
  bash stop_all_bots.sh
  ```
  - [ ] All bots stop cleanly
  - [ ] WebSocket connections closed properly
  - [ ] No errors in logs

### ⏳ Phase 9: Replit Integration Testing (NOT STARTED)
- [ ] Click "Stop" in Replit console
- [ ] Click "Run" in Replit console
  - [ ] All 3 bots start automatically
  - [ ] Startup notifications received
  - [ ] All show "RUNNING" status

### ⏳ Phase 10: Production Deployment (NOT STARTED)
- [ ] Enable Replit Always-On ($20/month subscription)
  - Without this, bots will sleep after ~30 minutes idle
- [ ] Monitor for 24 hours for stability
- [ ] Verify no unexpected restarts
- [ ] Check log file sizes

---

## 🚀 Quick Command Reference

### Launch & Control
```bash
# Start all bots (or click "Run" in Replit)
bash start_all_bots.sh

# Check status
bash status_all_bots.sh

# Restart specific bot
bash restart_bot.sh 3m
bash restart_bot.sh 15m
bash restart_bot.sh 1h

# Stop all bots gracefully
bash stop_all_bots.sh

# Health check
python3 health_check.py
```

### Monitoring
```bash
# Watch supervisor logs
tail -f logs/supervisord.log

# Watch individual bot logs
tail -f logs/extgap_indicator_3m_stdout.log
tail -f logs/extgap_indicator_15m_stdout.log
tail -f logs/extgap_indicator_1h_stdout.log

# Watch for errors
tail -f logs/extgap_indicator_*_stderr.log

# Monitor gap detections across all bots
tail -f logs/extgap_indicator_*_stdout.log | grep "gap detected"

# Monitor trade entries across all bots
tail -f logs/extgap_indicator_*_stdout.log | grep "Entry Executed"
```

### Troubleshooting
```bash
# Check supervisor status directly
supervisorctl -c supervisord.conf status

# Restart supervisor
supervisorctl -c supervisord.conf shutdown
bash start_all_bots.sh

# Kill stale supervisor processes
pkill -f supervisord
rm -f /tmp/supervisor.sock /tmp/supervisord.pid
bash start_all_bots.sh

# Test bot manually (bypass supervisor)
python3 binance_extgap_indicator_3m.py --timeframe 3m --log-level DEBUG
```

---

## 🔧 Troubleshooting Guide

### Problem: Supervisor won't start
**Symptoms:** `bash start_all_bots.sh` fails with "command not found"

**Solution:**
```bash
# Check if supervisor package installed
which supervisord

# If not found, trigger Replit package installation
# Click "Run" button in Replit (forces nix package install)
# Or manually trigger:
nix-env -i python311Packages.supervisor
```

### Problem: Bot won't start
**Symptoms:** Bot shows "BACKOFF" or "FATAL" in status

**Solution:**
```bash
# Check bot stderr logs
tail -50 logs/extgap_indicator_3m_stderr.log

# Test bot manually
python3 binance_extgap_indicator_3m.py --timeframe 3m --log-level DEBUG

# Common issues:
# - Missing .env credentials
# - Python dependencies not installed
# - Network connectivity issues
```

### Problem: No Telegram notifications
**Symptoms:** Bots running but no Telegram messages

**Solution:**
```bash
# Verify credentials loaded
source .env
echo $TELEGRAM_BOT_TOKEN_EXTGAP_3M
echo $TELEGRAM_CHAT_IDS_EXTGAP_3M

# Test Telegram bot API
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN_EXTGAP_3M}/getMe"

# Check bot logs for Telegram errors
grep -i "telegram\|notification" logs/extgap_indicator_3m_stdout.log
```

### Problem: Bots keep restarting
**Symptoms:** Rapid restart loop in supervisor logs

**Solution:**
```bash
# Check supervisor logs for error pattern
tail -100 logs/supervisord.log | grep -i error

# Check if bots crashing immediately
supervisorctl -c supervisord.conf status

# Increase startsecs in supervisord.conf if needed
# (currently 10s - bot must run 10s to be considered started)
```

### Problem: Replit sleeps and bots stop
**Symptoms:** Bots not running after Replit idle

**Solution:**
- **Recommended:** Enable Replit Always-On ($20/month)
- Alternative: Use Replit Deployments (separate from workspace)
- Not recommended: External keep-alive pings (unreliable)

---

## 📝 Next Steps

### Immediate Actions (Testing Phase)
1. **Test individual bots** in foreground mode to verify Telegram notifications
2. **Launch via supervisor** using `bash start_all_bots.sh`
3. **Verify all 3 bots running** with `bash status_all_bots.sh`
4. **Check Telegram channels** for startup notifications
5. **Test crash recovery** by killing one bot process
6. **Test graceful shutdown** with `bash stop_all_bots.sh`

### Production Deployment
1. **Enable Replit Always-On** to prevent sleep behavior
2. **Monitor for 24 hours** for stability
3. **Set up health checks** (optional: cron job running `health_check.py`)
4. **Document any issues** encountered

### Future Enhancements (Optional)
- Add more timeframes (10m, 30m, 4h)
- Implement Telegram command bot for remote control
- Add performance metrics dashboard
- Set up automated backups of CSV data
- Implement alerting for prolonged downtime

---

## 📚 Related Documentation

- `CLAUDE.md` - Complete project documentation
- `README.md` - Strategy explanation
- `QUICKSTART.md` - Quick start guide
- `supervisord.conf` - Process manager configuration
- `.replit` - Replit run configuration

---

## 💾 Context Recovery Instructions

**If this conversation is interrupted and you need to resume:**

1. **Read this file first** - It contains complete status of what's been done
2. **Check file existence** - All files listed in "Files Created" should exist
3. **Verify modifications** - All files listed in "Files Modified" should have the changes
4. **Review testing checklist** - See what testing remains to be done
5. **Use command reference** - Quick commands to check current state

**To verify current state:**
```bash
# Check if all files exist
ls -lh supervisord.conf start_all_bots.sh status_all_bots.sh stop_all_bots.sh restart_bot.sh health_check.py

# Check if bots are running
bash status_all_bots.sh 2>/dev/null || echo "Supervisor not running"

# Check recent git changes
git diff --name-only

# List recent log files
ls -lth logs/ | head -20
```

---

**End of Progress Document**
**Implementation:** ✅ Complete
**Testing:** ⏳ Pending
**Production:** ⏳ Not Deployed
