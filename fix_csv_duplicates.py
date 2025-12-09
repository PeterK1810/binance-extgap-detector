#!/usr/bin/env python3
"""
Fix duplicate entries in CSV files and recalculate cumulative stats.
"""

import csv
from pathlib import Path

def remove_duplicates_and_recalculate(csv_path):
    """Remove duplicate trades and recalculate cumulative statistics."""
    fieldnames = [
        'Status', 'Open Time', 'Close Time', 'Market', 'Side', 'Entry Price', 'Exit Price',
        'Position Size ($)', 'Position Size (Qty)', 'Gross P&L', 'Realized P&L', 'Total Fees',
        'Close Reason', 'Cumulative Wins', 'Cumulative Losses', 'Cumulative P&L', 'Cumulative Fees'
    ]

    # Read all trades
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        trades = list(reader)

    print(f"Read {len(trades)} trades from {csv_path}")

    # Remove duplicates (same Open Time + Side)
    seen = set()
    unique_trades = []
    for trade in trades:
        key = (trade['Open Time'], trade['Side'], trade['Entry Price'])
        if key not in seen:
            seen.add(key)
            unique_trades.append(trade)
        else:
            print(f"  Removing duplicate: {trade['Open Time']} {trade['Side']}")

    print(f"After removing duplicates: {len(unique_trades)} trades")

    # Recalculate cumulative statistics
    cum_wins = 0
    cum_losses = 0
    cum_pnl = 0.0
    cum_fees = 0.0

    for trade in unique_trades:
        realized_pnl = float(trade['Realized P&L'])
        fees = float(trade['Total Fees'])

        if trade['Status'] == 'WIN':
            cum_wins += 1
        elif trade['Status'] == 'LOSS':
            cum_losses += 1

        cum_pnl += realized_pnl
        cum_fees += fees

        trade['Cumulative Wins'] = cum_wins
        trade['Cumulative Losses'] = cum_losses
        trade['Cumulative P&L'] = round(cum_pnl, 2)
        trade['Cumulative Fees'] = round(cum_fees, 2)

    # Write back
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unique_trades)

    print(f"Written {len(unique_trades)} trades to {csv_path}")
    print(f"Final stats: {cum_wins} wins, {cum_losses} losses, P&L: ${cum_pnl:.2f}")

    return unique_trades


def main():
    base_path = Path('/mnt/c/Users/conna/Desktop/binance-extgap-detector-V1')

    print("=" * 60)
    print("Fixing 15m CSV...")
    print("=" * 60)
    csv_15m = base_path / 'data' / 'indicators' / 'trades' / 'binance_extgap_15m_trades.csv'
    trades_15m = remove_duplicates_and_recalculate(csv_15m)

    print("\n" + "=" * 60)
    print("Fixing 1h CSV...")
    print("=" * 60)
    csv_1h = base_path / 'data' / 'indicators' / 'trades' / 'binance_extgap_1h_trades.csv'
    trades_1h = remove_duplicates_and_recalculate(csv_1h)


if __name__ == '__main__':
    main()
