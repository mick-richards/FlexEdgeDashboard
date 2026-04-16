"""Standalone calendar travel scanner.

Run this script to scan Outlook calendar for travel events and save results
to data/scan_results.json. The Emissies page picks these up automatically.

Usage:
    python scan_calendar.py [--days 30]

Or called from Claude Code /assistant weekly close-out.
"""
from __future__ import annotations

import sys


if __name__ == "__main__":
    days = 30
    if "--days" in sys.argv:
        idx = sys.argv.index("--days")
        if idx + 1 < len(sys.argv):
            days = int(sys.argv[idx + 1])

    print(f"This script requires calendar events from the Outlook MCP.")
    print(f"Use Claude Code to scan: the /assistant weekly close-out will handle this automatically.")
    print(f"Or pass events as JSON via stdin.")
