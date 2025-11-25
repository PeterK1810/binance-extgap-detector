#!/usr/bin/env python3
"""
Health check script for external gap indicator bots

This script checks if all 3 bots (3m, 15m, 1h) are running properly via supervisord.
Returns exit code 0 if all healthy, 1 if any failures.

Usage:
    python3 health_check.py
"""

import subprocess
import sys
from datetime import datetime, timezone


def check_supervisor_status():
    """Check if all bots are running via supervisord"""
    try:
        result = subprocess.run(
            ['supervisorctl', '-c', 'supervisord.conf', 'status'],
            capture_output=True,
            text=True,
            timeout=10
        )

        output = result.stdout

        # Check each bot
        bots = ['extgap_3m', 'extgap_15m', 'extgap_1h']
        running = []
        failed = []

        for bot in bots:
            # Supervisor status format: "extgap_3m    RUNNING   pid 12345, uptime 0:01:23"
            if f"{bot:20}RUNNING" in output or f"{bot}  RUNNING" in output or "RUNNING" in output.split(bot)[1].split('\n')[0] if bot in output else False:
                running.append(bot)
            else:
                failed.append(bot)

        return running, failed

    except subprocess.TimeoutExpired:
        return [], ["Timeout: supervisorctl not responding"]
    except FileNotFoundError:
        return [], ["Error: supervisorctl command not found"]
    except Exception as e:
        return [], [f"Error: {e}"]


def main():
    """Main health check routine"""
    print(f"Health Check - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    running, failed = check_supervisor_status()

    if failed:
        print(f"❌ FAILED BOTS: {', '.join(failed)}")
        print(f"✅ RUNNING BOTS: {', '.join(running) if running else 'None'}")
        sys.exit(1)
    else:
        print(f"✅ All bots running: {', '.join(running)}")
        print("📊 System healthy")
        sys.exit(0)


if __name__ == "__main__":
    main()
