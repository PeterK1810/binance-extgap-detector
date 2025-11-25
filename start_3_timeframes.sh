#!/bin/bash
# Multi-timeframe launcher for Reserved VM deployment
# Runs 3m, 5m, 15m, and 1h trading bots and keeps the main process alive

set -e

cd /home/runner/workspace

echo "=========================================="
echo "External Gap Indicator - Multi-Timeframe Launcher"
echo "=========================================="
echo ""

trap 'echo "Shutting down all bots..."; kill $(jobs -p) 2>/dev/null; exit 0' SIGTERM SIGINT

PIDS=()

mkdir -p logs data

echo "🚀 Starting 3m bot..."
python3 binance_extgap_indicator_3m.py \
    --symbol BTCUSDT \
    --timeframe 3m \
    --output data/binance_extgap_3m_gaps.csv \
    --trades-output data/binance_extgap_3m_trades.csv \
    >> logs/extgap_indicator_3m.log 2>&1 &
PID_3M=$!
PIDS+=($PID_3M)
echo "   Started 3m with PID: $PID_3M"
sleep 3

echo "🚀 Starting 5m bot..."
python3 binance_extgap_indicator_5m.py \
    --symbol BTCUSDT \
    --timeframe 5m \
    --output data/binance_extgap_5m_gaps.csv \
    --trades-output data/binance_extgap_5m_trades.csv \
    >> logs/extgap_indicator_5m.log 2>&1 &
PID_5M=$!
PIDS+=($PID_5M)
echo "   Started 5m with PID: $PID_5M"
sleep 3

echo "🚀 Starting 15m bot..."
python3 binance_extgap_indicator_15m.py \
    --symbol BTCUSDT \
    --timeframe 15m \
    --output data/binance_extgap_15m_gaps.csv \
    --trades-output data/binance_extgap_15m_trades.csv \
    >> logs/extgap_indicator_15m.log 2>&1 &
PID_15M=$!
PIDS+=($PID_15M)
echo "   Started 15m with PID: $PID_15M"
sleep 3

echo "🚀 Starting 1h bot..."
python3 binance_extgap_indicator_1h.py \
    --symbol BTCUSDT \
    --timeframe 1h \
    --output data/binance_extgap_1h_gaps.csv \
    --trades-output data/binance_extgap_1h_trades.csv \
    >> logs/extgap_indicator_1h.log 2>&1 &
PID_1H=$!
PIDS+=($PID_1H)
echo "   Started 1h with PID: $PID_1H"

echo ""
echo "=========================================="
echo "✅ All 4 bots launched!"
echo "   3m PID: $PID_3M"
echo "   5m PID: $PID_5M"
echo "   15m PID: $PID_15M"
echo "   1h PID: $PID_1H"
echo "=========================================="
echo ""

# Check if all processes started successfully
sleep 2
for pid in "${PIDS[@]}"; do
    if ! ps -p $pid > /dev/null 2>&1; then
        echo "⚠️  WARNING: Process $pid has already exited!"
    fi
done

echo "Keeping main process alive to maintain deployment..."
echo "Press Ctrl+C to stop all bots"
echo ""

# Wait for all background processes
wait "${PIDS[@]}"

echo "All processes have exited"
