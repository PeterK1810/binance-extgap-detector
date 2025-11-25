# External Gap Indicator Trading System

Real-time gap detection and trading bot for Binance Futures using WebSocket streams.

## Quick Start

```bash
# Start all bots
bash scripts/management/start_all_bots.sh

# Check status
bash scripts/management/status_all_bots.sh

# Stop all bots
bash scripts/management/stop_all_bots.sh
```

## Directory Structure

```
/
├── bots/              # Trading bot source code
│   ├── indicators/    # Production trading bots (3m, 5m, 15m, 1h)
│   ├── detectors/     # Pure detection bots (v1, v2, v3)
│   └── legacy/        # Archived old versions
├── scripts/           # Management and utility scripts
│   ├── management/    # Start/stop/status scripts
│   └── utils/         # Helper utilities
├── data/              # Trading data outputs
│   ├── indicators/    # Gap and trade CSVs from indicators
│   ├── detectors/     # Gap CSVs from detectors
│   └── archive/       # Old/test data
├── logs/              # Bot and system logs
│   ├── indicators/    # Indicator bot logs
│   ├── detectors/     # Detector bot logs
│   ├── supervisor/    # Supervisord logs
│   └── archive/       # Rotated logs
├── config/            # Configuration files
│   ├── supervisord.conf
│   ├── .env
│   └── .env.example
└── docs/              # Complete documentation
    ├── README.md      # Full project documentation
    ├── CLAUDE.md      # Development guide
    ├── QUICKSTART.md  # Getting started guide
    └── ...
```

## Documentation

For complete documentation, see:
- [Full README](docs/README.md) - Complete project documentation
- [CLAUDE.md](docs/CLAUDE.md) - Development and implementation guide
- [QUICKSTART.md](docs/QUICKSTART.md) - Step-by-step startup guide
- [COMMANDS.txt](docs/COMMANDS.txt) - Command reference

## Features

- Real-time WebSocket gap detection
- Multi-timeframe support (3m, 5m, 15m, 1h)
- Automated position reversal
- French-language Telegram notifications
- Supervisord process management
- CSV data logging for analysis

## License

Proprietary - All rights reserved
