#!/usr/bin/env python3
"""
Parse Telegram HTML exports to extract trade data and update CSV files.
"""

import re
import csv
from datetime import datetime
from pathlib import Path

def parse_telegram_html(html_path, timeframe):
    """Parse Telegram HTML file and extract trade data."""
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    trades = []

    # Find all entry messages (ENTRÉE LONG/SHORT)
    entry_pattern = r'title="(\d+\.\d+\.\d+)\s+(\d+:\d+:\d+)\s+UTC\+01:00"[^>]*>[^<]*</div>[^<]*<div class="text">[^<]*📈 <strong>ENTRÉE LONG #\d+ - BTCUSDT</strong>.*?⏰ ([\d:]+) UTC.*?Prix d&apos;entrée: <strong>([\d,\.]+) USDT</strong>.*?Position: \$([\d,\.]+).*?Quantité: ([\d\.]+) BTC'
    short_entry_pattern = r'title="(\d+\.\d+\.\d+)\s+(\d+:\d+:\d+)\s+UTC\+01:00"[^>]*>[^<]*</div>[^<]*<div class="text">[^<]*📉 <strong>ENTRÉE SHORT #\d+ - BTCUSDT</strong>.*?⏰ ([\d:]+) UTC.*?Prix d&apos;entrée: <strong>([\d,\.]+) USDT</strong>.*?Position: \$([\d,\.]+).*?Quantité: ([\d\.]+) BTC'

    # Find all inversion messages (INVERSION DE TENDANCE) which contain P&L
    inversion_pattern = r'title="(\d+\.\d+\.\d+)\s+(\d+:\d+:\d+)\s+UTC\+01:00"[^>]*>[^<]*</div>[^<]*<div class="text">[^<]*🔄 <strong>INVERSION DE TENDANCE - BTCUSDT</strong>.*?⏰ ([\d:]+) UTC.*?P&amp;L Position Fermée:</strong>.*?(✅|❌) (LONG|SHORT): <strong>([+-]?[\d\.]+) USD \(([+-]?[\d\.]+)%\)</strong>.*?Entrée: ([\d,\.]+) → Sortie: ([\d,\.]+).*?Quantité: ([\d\.]+) BTC'

    # Alternative simpler patterns
    entry_msgs = re.findall(
        r'📈 <strong>ENTRÉE LONG #\d+ - BTCUSDT</strong>.*?⏰ ([\d:]+) UTC.*?Prix d&apos;entrée: <strong>([\d,\.]+) USDT</strong>.*?Position: \$([\d,\.]+).*?Quantité: ([\d\.]+) BTC',
        content, re.DOTALL
    )

    short_entry_msgs = re.findall(
        r'📉 <strong>ENTRÉE SHORT #\d+ - BTCUSDT</strong>.*?⏰ ([\d:]+) UTC.*?Prix d&apos;entrée: <strong>([\d,\.]+) USDT</strong>.*?Position: \$([\d,\.]+).*?Quantité: ([\d\.]+) BTC',
        content, re.DOTALL
    )

    inversion_msgs = re.findall(
        r'🔄 <strong>INVERSION DE TENDANCE - BTCUSDT</strong>.*?⏰ ([\d:]+) UTC.*?P&amp;L Position Fermée:</strong>.*?(✅|❌) (LONG|SHORT): <strong>([+-]?[\d\.]+) USD \(([+-]?[\d\.]+)%\)</strong>.*?Entrée: ([\d,\.]+) → Sortie: ([\d,\.]+).*?Quantité: ([\d\.]+) BTC',
        content, re.DOTALL
    )

    print(f"\nFound {len(entry_msgs)} LONG entries")
    print(f"Found {len(short_entry_msgs)} SHORT entries")
    print(f"Found {len(inversion_msgs)} inversions (closed trades)")

    # Now extract with dates from title attributes
    # Pattern to find message blocks with dates and inversions
    blocks = re.findall(
        r'title="(\d+)\.(\d+)\.(\d+)\s+(\d+):(\d+):(\d+)\s+UTC\+01:00"[^>]*>.*?<div class="text">(.*?)</div>',
        content, re.DOTALL
    )

    all_entries = []
    all_closures = []

    for day, month, year, hour, minute, second, text in blocks:
        # Convert UTC+01 to UTC (subtract 1 hour)
        utc_dt = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
        # Adjust for timezone - subtract 1 hour for UTC
        from datetime import timedelta
        utc_dt = utc_dt - timedelta(hours=1)

        # Check for LONG entry
        long_match = re.search(
            r'📈 <strong>ENTRÉE LONG #\d+ - BTCUSDT</strong>.*?Prix d&apos;entrée: <strong>([\d,\.]+) USDT</strong>.*?Quantité: ([\d\.]+) BTC',
            text, re.DOTALL
        )
        if long_match:
            entry_price = float(long_match.group(1).replace(',', ''))
            qty = float(long_match.group(2))
            all_entries.append({
                'datetime': utc_dt,
                'side': 'LONG',
                'entry_price': entry_price,
                'qty': qty,
                'position_size': 1000.00
            })

        # Check for SHORT entry
        short_match = re.search(
            r'📉 <strong>ENTRÉE SHORT #\d+ - BTCUSDT</strong>.*?Prix d&apos;entrée: <strong>([\d,\.]+) USDT</strong>.*?Quantité: ([\d\.]+) BTC',
            text, re.DOTALL
        )
        if short_match:
            entry_price = float(short_match.group(1).replace(',', ''))
            qty = float(short_match.group(2))
            all_entries.append({
                'datetime': utc_dt,
                'side': 'SHORT',
                'entry_price': entry_price,
                'qty': qty,
                'position_size': 1000.00
            })

        # Check for closure (INVERSION)
        closure_match = re.search(
            r'🔄 <strong>INVERSION DE TENDANCE.*?P&amp;L Position Fermée:</strong>.*?(✅|❌) (LONG|SHORT): <strong>([+-]?[\d\.]+) USD.*?Entrée: ([\d,\.]+) → Sortie: ([\d,\.]+).*?Quantité: ([\d\.]+) BTC',
            text, re.DOTALL
        )
        if closure_match:
            status_icon = closure_match.group(1)
            side = closure_match.group(2)
            gross_pnl = float(closure_match.group(3))
            entry = float(closure_match.group(4).replace(',', ''))
            exit_price = float(closure_match.group(5).replace(',', ''))
            qty = float(closure_match.group(6))
            all_closures.append({
                'datetime': utc_dt,
                'side': side,
                'gross_pnl': gross_pnl,
                'entry_price': entry,
                'exit_price': exit_price,
                'qty': qty,
                'status': 'WIN' if status_icon == '✅' else 'LOSS'
            })

    print(f"Parsed {len(all_entries)} entry records")
    print(f"Parsed {len(all_closures)} closure records")

    # Match entries with closures to build complete trades
    trades = []

    # Sort entries and closures by datetime
    all_entries.sort(key=lambda x: x['datetime'])
    all_closures.sort(key=lambda x: x['datetime'])

    # Match closures with their corresponding entry
    for closure in all_closures:
        # Find the most recent entry that matches the side and has no closure yet
        matching_entry = None
        for entry in reversed(all_entries):
            if entry['datetime'] < closure['datetime'] and entry['side'] == closure['side']:
                # Check if entry price matches approximately
                if abs(entry['entry_price'] - closure['entry_price']) < 1.0:
                    matching_entry = entry
                    break

        if matching_entry:
            # Fees: 0.03% per side = 0.06% total = $0.60 on $1000
            total_fees = 0.60
            realized_pnl = closure['gross_pnl'] - total_fees
            status = 'WIN' if realized_pnl > 0 else 'LOSS'

            trades.append({
                'Status': status,
                'Open Time': matching_entry['datetime'].strftime('%Y-%m-%dT%H:%M:%S+00:00'),
                'Close Time': closure['datetime'].strftime('%Y-%m-%dT%H:%M:%S+00:00'),
                'Market': 'BTCUSDT',
                'Side': closure['side'],
                'Entry Price': closure['entry_price'],
                'Exit Price': closure['exit_price'],
                'Position Size ($)': 1000.00,
                'Position Size (Qty)': closure['qty'],
                'Gross P&L': round(closure['gross_pnl'], 2),
                'Realized P&L': round(realized_pnl, 2),
                'Total Fees': total_fees,
                'Close Reason': 'REVERSE'
            })

    # Check for open position (last entry without closure)
    if all_entries:
        last_entry = all_entries[-1]
        # Check if there's a closure after this entry
        has_closure = False
        for closure in all_closures:
            if closure['datetime'] > last_entry['datetime'] and closure['side'] == last_entry['side']:
                has_closure = True
                break

        if not has_closure:
            trades.append({
                'Status': 'OPEN',
                'Open Time': last_entry['datetime'].strftime('%Y-%m-%dT%H:%M:%S+00:00'),
                'Close Time': '',
                'Market': 'BTCUSDT',
                'Side': last_entry['side'],
                'Entry Price': last_entry['entry_price'],
                'Exit Price': '',
                'Position Size ($)': 1000.00,
                'Position Size (Qty)': last_entry['qty'],
                'Gross P&L': 0.00,
                'Realized P&L': 0.00,
                'Total Fees': 0.00,
                'Close Reason': 'PENDING'
            })

    return trades


def calculate_cumulative_stats(trades, existing_stats=None):
    """Calculate cumulative statistics for trades."""
    if existing_stats:
        cum_wins = existing_stats['wins']
        cum_losses = existing_stats['losses']
        cum_pnl = existing_stats['pnl']
        cum_fees = existing_stats['fees']
    else:
        cum_wins = 0
        cum_losses = 0
        cum_pnl = 0.0
        cum_fees = 0.0

    for trade in trades:
        if trade['Status'] == 'WIN':
            cum_wins += 1
        elif trade['Status'] == 'LOSS':
            cum_losses += 1

        cum_pnl += trade['Realized P&L']
        cum_fees += trade['Total Fees']

        trade['Cumulative Wins'] = cum_wins
        trade['Cumulative Losses'] = cum_losses
        trade['Cumulative P&L'] = round(cum_pnl, 2)
        trade['Cumulative Fees'] = round(cum_fees, 2)

    return trades


def read_existing_csv(csv_path):
    """Read existing CSV and return last cumulative stats."""
    stats = {'wins': 0, 'losses': 0, 'pnl': 0.0, 'fees': 0.0}
    last_time = None

    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if rows:
                last_row = rows[-1]
                stats['wins'] = int(last_row.get('Cumulative Wins', 0))
                stats['losses'] = int(last_row.get('Cumulative Losses', 0))
                stats['pnl'] = float(last_row.get('Cumulative P&L', 0))
                stats['fees'] = float(last_row.get('Cumulative Fees', 0))
                last_time = last_row.get('Open Time', '')
    except FileNotFoundError:
        pass

    return stats, last_time, rows if 'rows' in dir() else []


def write_csv(csv_path, trades, fieldnames):
    """Write trades to CSV file."""
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trades)


def main():
    base_path = Path('/mnt/c/Users/conna/Desktop/binance-extgap-detector-V1')
    telegram_path = Path('/mnt/c/Users/conna/Downloads/Telegram Desktop')

    fieldnames = [
        'Status', 'Open Time', 'Close Time', 'Market', 'Side', 'Entry Price', 'Exit Price',
        'Position Size ($)', 'Position Size (Qty)', 'Gross P&L', 'Realized P&L', 'Total Fees',
        'Close Reason', 'Cumulative Wins', 'Cumulative Losses', 'Cumulative P&L', 'Cumulative Fees'
    ]

    # Process 15m trades
    print("=" * 50)
    print("Processing 15m trades...")
    print("=" * 50)

    html_15m = telegram_path / 'ChatExport_2025-12-01' / 'messages.html'
    csv_15m = base_path / 'data' / 'indicators' / 'trades' / 'binance_extgap_15m_trades.csv'

    existing_stats_15m, last_time_15m, existing_trades_15m = read_existing_csv(csv_15m)
    print(f"Existing 15m stats: {existing_stats_15m}, last time: {last_time_15m}")

    trades_15m = parse_telegram_html(html_15m, '15m')
    print(f"\nExtracted {len(trades_15m)} trades from Telegram")

    # Filter only new trades (after last existing trade)
    if last_time_15m:
        new_trades_15m = [t for t in trades_15m if t['Open Time'] > last_time_15m]
        print(f"New trades to add: {len(new_trades_15m)}")
    else:
        new_trades_15m = trades_15m

    # Calculate cumulative stats for new trades
    if new_trades_15m:
        new_trades_15m = calculate_cumulative_stats(new_trades_15m, existing_stats_15m)

        # Combine existing and new trades
        all_trades_15m = existing_trades_15m + new_trades_15m

        # Write to CSV
        write_csv(csv_15m, all_trades_15m, fieldnames)
        print(f"Written {len(all_trades_15m)} trades to {csv_15m}")

    # Process 1h trades
    print("\n" + "=" * 50)
    print("Processing 1h trades...")
    print("=" * 50)

    html_1h = telegram_path / 'ChatExport_2025-12-01 (1)' / 'messages.html'
    csv_1h = base_path / 'data' / 'indicators' / 'trades' / 'binance_extgap_1h_trades.csv'

    existing_stats_1h, last_time_1h, existing_trades_1h = read_existing_csv(csv_1h)
    print(f"Existing 1h stats: {existing_stats_1h}, last time: {last_time_1h}")

    trades_1h = parse_telegram_html(html_1h, '1h')
    print(f"\nExtracted {len(trades_1h)} trades from Telegram")

    # Filter only new trades
    if last_time_1h:
        new_trades_1h = [t for t in trades_1h if t['Open Time'] > last_time_1h]
        print(f"New trades to add: {len(new_trades_1h)}")
    else:
        new_trades_1h = trades_1h

    # Calculate cumulative stats
    if new_trades_1h:
        new_trades_1h = calculate_cumulative_stats(new_trades_1h, existing_stats_1h)

        # Combine existing and new trades
        all_trades_1h = existing_trades_1h + new_trades_1h

        # Write to CSV
        write_csv(csv_1h, all_trades_1h, fieldnames)
        print(f"Written {len(all_trades_1h)} trades to {csv_1h}")

    # Print summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    # 15m summary
    print("\n15m Timeframe:")
    if new_trades_15m:
        wins = sum(1 for t in new_trades_15m if t['Status'] == 'WIN')
        losses = sum(1 for t in new_trades_15m if t['Status'] == 'LOSS')
        total_pnl = sum(t['Realized P&L'] for t in new_trades_15m)
        print(f"  New trades added: {len(new_trades_15m)}")
        print(f"  Wins: {wins}, Losses: {losses}")
        print(f"  Total P&L: ${total_pnl:.2f}")

    # 1h summary
    print("\n1h Timeframe:")
    if new_trades_1h:
        wins = sum(1 for t in new_trades_1h if t['Status'] == 'WIN')
        losses = sum(1 for t in new_trades_1h if t['Status'] == 'LOSS')
        total_pnl = sum(t['Realized P&L'] for t in new_trades_1h)
        print(f"  New trades added: {len(new_trades_1h)}")
        print(f"  Wins: {wins}, Losses: {losses}")
        print(f"  Total P&L: ${total_pnl:.2f}")


if __name__ == '__main__':
    main()
