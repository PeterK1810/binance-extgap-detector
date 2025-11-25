# Multi-Timeframe Gap Detector - Deployment Status

## ✅ All 4 Timeframes Running

| Timeframe | Status | PID | WebSocket | Telegram Chats |
|-----------|--------|-----|-----------|----------------|
| **3m** | ✅ Running | 15356 | Connected | 2 |
| **5m** | ✅ Running | 15390 | Connected | 2 |
| **15m** | ✅ Running | 15411 | Connected | 2 |
| **1h** | ✅ Running | 15418 | Connected | 2 |

## Telegram Credentials

### 3m Timeframe
- **Bot Token**: 8586866654:AAF6hoImqAM46hhsfEFm0898ZNpFTqEZGKw
- **Chat IDs**: -1003358731201, 1474566688

### 5m Timeframe
- **Bot Token**: 8204135201:AAE7EMJP7aFGKR4NuJ5E90DpGaqEDvXRg3U
- **Chat IDs**: -1003203997188, 1474566688

### 15m Timeframe
- **Bot Token**: 8257546943:AAHFfRKns6u8VdOPzB1mjdCY1K7kYgomcY8
- **Chat IDs**: -1003208418021, 1474566688

### 1h Timeframe
- **Bot Token**: 8146581274:AAH9AzQzhttftcaiJbrnyRkUY4z2ZOpQJd0
- **Chat IDs**: -1002985538408, 1474566688

## Deployment Configuration

- **Type**: Reserved VM (99.9% uptime)
- **Run Command**: `./start_3_timeframes.sh`
- **Environment**: All credentials stored in shared environment variables

## Log Files

- 3m: `logs/extgap_indicator_3m.log`
- 5m: `logs/extgap_indicator_5m.log`
- 15m: `logs/extgap_indicator_15m.log`
- 1h: `logs/extgap_indicator_1h.log`

## Data Files

- 3m gaps: `data/binance_extgap_3m_gaps.csv`
- 3m trades: `data/binance_extgap_3m_trades.csv`
- 5m gaps: `data/binance_extgap_5m_gaps.csv`
- 5m trades: `data/binance_extgap_5m_trades.csv`
- 15m gaps: `data/binance_extgap_15m_gaps.csv`
- 15m trades: `data/binance_extgap_15m_trades.csv`
- 1h gaps: `data/binance_extgap_1h_gaps.csv`
- 1h trades: `data/binance_extgap_1h_trades.csv`

## Status Check Commands

```bash
# Check all running bots
ps aux | grep binance_extgap_indicator | grep -v grep

# View logs
tail -f logs/extgap_indicator_3m.log
tail -f logs/extgap_indicator_5m.log
tail -f logs/extgap_indicator_15m.log
tail -f logs/extgap_indicator_1h.log

# Check latest activity
for tf in 3m 5m 15m 1h; do echo "=== $tf ==="; tail -5 logs/extgap_indicator_${tf}.log; echo ""; done
```

## Next Steps

1. **Publish to Reserved VM**: Click "Publish" button in Replit to deploy to production
2. **Monitor Telegram**: You should receive notifications when gaps are detected
3. **Check Logs**: Monitor the log files for any issues

