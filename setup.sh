#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  DPS Daily School Summary — One-Time Setup Script
#  Run this once to install dependencies and schedule the daily 7 PM email.
#
#  Usage:
#    chmod +x setup.sh
#    ./setup.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/dps_daily_summary.py"
ENV_PATH="$SCRIPT_DIR/.env"
LOG_PATH="$SCRIPT_DIR/dps_summary.log"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  DPS Daily School Summary — Setup"
echo "═══════════════════════════════════════════════════"
echo ""

# ── Step 1: Check Python ───────────────────────────────────────────────────────
echo "▶ Checking Python 3..."
if ! command -v python3 &>/dev/null; then
  echo "  ✗ Python 3 not found."
  echo "    Install it from https://www.python.org/downloads/"
  exit 1
fi
PYTHON=$(command -v python3)
echo "  ✓ Found: $PYTHON ($($PYTHON --version))"

# ── Step 2: Install pip dependencies ──────────────────────────────────────────
echo ""
echo "▶ Installing Python dependencies..."
$PYTHON -m pip install --upgrade pip --quiet
$PYTHON -m pip install playwright python-dotenv --quiet
echo "  ✓ playwright and python-dotenv installed"

echo ""
echo "▶ Installing Playwright browsers (Chromium)..."
$PYTHON -m playwright install chromium
echo "  ✓ Chromium installed"

# ── Step 3: Create .env if it doesn't exist ───────────────────────────────────
echo ""
if [ ! -f "$ENV_PATH" ]; then
  echo "▶ Creating .env from template..."
  cp "$SCRIPT_DIR/.env.template" "$ENV_PATH"
  echo "  ✓ Created: $ENV_PATH"
  echo ""
  echo "  ┌──────────────────────────────────────────────────────┐"
  echo "  │  ACTION REQUIRED: Open .env and fill in your info:   │"
  echo "  │                                                       │"
  echo "  │  DPS_USERNAME      = your Infinite Campus username    │"
  echo "  │  DPS_PASSWORD      = your Infinite Campus password    │"
  echo "  │  GMAIL_APP_PASSWORD= your Gmail App Password          │"
  echo "  │  STUDENT_NAME      = your child's name                │"
  echo "  │                                                       │"
  echo "  │  Get a Gmail App Password at:                         │"
  echo "  │  https://myaccount.google.com → Security →            │"
  echo "  │  2-Step Verification → App passwords                  │"
  echo "  └──────────────────────────────────────────────────────┘"
  echo ""
  read -p "  Press Enter after you've filled in .env to continue..."
else
  echo "▶ .env already exists — skipping template copy."
fi

# ── Step 4: Test run (optional) ───────────────────────────────────────────────
echo ""
read -p "▶ Would you like to do a test run now? (y/n): " TEST_RUN
if [[ "$TEST_RUN" == "y" || "$TEST_RUN" == "Y" ]]; then
  echo "  Running test... (this may take 30–60 seconds)"
  $PYTHON "$SCRIPT_PATH" && echo "  ✓ Test run succeeded!" || echo "  ✗ Test run failed — check your .env credentials."
fi

# ── Step 5: Schedule daily cron at 7 PM ───────────────────────────────────────
echo ""
echo "▶ Scheduling daily run at 7:00 PM..."

CRON_CMD="0 19 * * * $PYTHON $SCRIPT_PATH >> $LOG_PATH 2>&1"
CRON_COMMENT="# DPS Daily School Summary"

# Check if cron entry already exists
if crontab -l 2>/dev/null | grep -q "dps_daily_summary.py"; then
  echo "  ℹ Cron job already exists — skipping."
else
  # Add to crontab
  (crontab -l 2>/dev/null; echo "$CRON_COMMENT"; echo "$CRON_CMD") | crontab -
  echo "  ✓ Cron job added: runs every day at 7:00 PM"
fi

# Restrict log file to owner-only access
touch "$LOG_PATH"
chmod 600 "$LOG_PATH"

# ── Summary ───────────────────────────────────────────────────────────────────
# Read recipient from .env for display (avoid hardcoding PII in this script)
RECIPIENT=$(grep -E '^RECIPIENT_EMAIL=' "$ENV_PATH" 2>/dev/null | head -1 | cut -d= -f2- | tr ',' ' ' | awk '{print $1}')

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✓ Setup complete!"
echo ""
echo "  The summary will email to: ${RECIPIENT:-<see RECIPIENT_EMAIL in .env>}"
echo "  Schedule: Every day at 7:00 PM"
echo "  Log file: $LOG_PATH"
echo ""
echo "  To run manually anytime:"
echo "    python3 $SCRIPT_PATH"
echo ""
echo "  To view the cron schedule:"
echo "    crontab -l"
echo ""
echo "  To remove the schedule:"
echo "    crontab -e   (delete the DPS line)"
echo "═══════════════════════════════════════════════════"
echo ""
