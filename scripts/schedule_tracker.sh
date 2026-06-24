#!/usr/bin/env bash
# schedule_tracker.sh
# Adds a cron job to run the tracker every 15 minutes.
# Run once: bash scripts/schedule_tracker.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="$(command -v python3 || command -v python)"
LOG="$PROJECT_DIR/cron_tracker.log"

CRON_CMD="*/15 * * * * cd $PROJECT_DIR && $PYTHON tracker.py >> $LOG 2>&1"

# Add only if not already present
( crontab -l 2>/dev/null | grep -v "tracker.py" ; echo "$CRON_CMD" ) | crontab -

echo "Cron job installed:"
crontab -l | grep "tracker.py"
echo ""
echo "Tracker will run every 15 minutes. Logs → $LOG"
