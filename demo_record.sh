#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Codex Guardian — Demo Screen Recorder
# Starts a QuickTime screen recording, launches the dashboard, and opens
# the terminal layout ready for the demo. When you're done, press any key
# and the script stops the recording and saves it to ~/Desktop.
#
# Usage:
#   chmod +x demo_record.sh
#   ./demo_record.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"
SAVE_PATH="$HOME/Desktop/codex-guardian-demo-$TIMESTAMP.mov"
DASHBOARD_URL="http://localhost:8080"

# ── Colors ────────────────────────────────────────────────────────────────────
BOLD='\033[1m'
CYAN='\033[0;36m'
AMBER='\033[0;33m'
GREEN='\033[0;32m'
RESET='\033[0m'

header() { echo -e "\n${AMBER}${BOLD}▶  $1${RESET}"; }
step()   { echo -e "   ${CYAN}$1${RESET}"; }
ok()     { echo -e "   ${GREEN}✓ $1${RESET}"; }

echo ""
echo -e "${BOLD}╔═══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║        CODEX GUARDIAN — DEMO RECORDER                ║${RESET}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════════╝${RESET}"

# ── Step 1: Kill any existing server and start fresh ─────────────────────────
header "Preparing server"

if lsof -i :8080 -sTCP:LISTEN -t &>/dev/null; then
    step "Stopping existing server on port 8080..."
    lsof -i :8080 -sTCP:LISTEN -t | xargs kill 2>/dev/null || true
    sleep 0.5
fi

# Clear any stale pipeline_status.json from a previous run
rm -f "$SCRIPT_DIR/pipeline_status.json"
ok "Cleared stale pipeline status"

step "Starting dashboard server..."
cd "$SCRIPT_DIR"
python3 server.py &
SERVER_PID=$!
sleep 1

# Verify server is up
if ! curl -s "$DASHBOARD_URL" > /dev/null; then
    echo "  ERROR: Server failed to start. Check server.py."
    exit 1
fi
ok "Server running at $DASHBOARD_URL (PID $SERVER_PID)"

# ── Step 2: Open dashboard in browser ────────────────────────────────────────
header "Opening dashboard in browser"
open "$DASHBOARD_URL"
sleep 1.5
ok "Dashboard open"

# ── Step 3: Start QuickTime screen recording ─────────────────────────────────
header "Starting screen recording"
step "Launching QuickTime Player..."

osascript <<'APPLESCRIPT'
tell application "QuickTime Player"
    activate
    -- Start a new screen recording
    set newRecording to (new screen recording)
    tell newRecording
        start
    end tell
end tell
APPLESCRIPT

sleep 2
ok "QuickTime recording started — click the ● record button in the QuickTime toolbar if it hasn't started automatically"

# ── Step 4: Print the demo run sequence ──────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  DEMO SEQUENCE — run these in order${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${AMBER}SCENE 1${RESET} — Dashboard overview (no commands, just pan around)"
echo -e "           Point to: KPIs, Pipeline diagram, Latest Incident card"
echo ""
echo -e "  ${AMBER}SCENE 2${RESET} — Auto-handle run (fast, no gates)"
echo -e "           ${CYAN}python3 backtest.py 2${RESET}   ← alert-003, LOW, staging"
echo -e "           Watch: dashboard stage badge shows ALERT→CONTEXT→FRESHNESS→ROUTER→DEPLOY"
echo ""
echo -e "  ${AMBER}SCENE 3${RESET} — HIGH risk escalation run (manual — you type at gates)"
echo -e "           ${CYAN}python3 main.py 0${RESET}       ← alert-001, HIGH, auth-service"
echo -e "           Gate 1 handle : @yourname"
echo -e "           Gate 1 choice : type '1' (or whichever hypothesis)"
echo -e "           Gate 2 handle : @yourname"
echo -e "           Gate 2 choice : type 'approve'"
echo -e "           Gate 2 reason : Reviewed diff — connection pool fix is scoped and safe"
echo ""
echo -e "  ${AMBER}SCENE 4${RESET} — Dashboard walkthrough after the run"
echo -e "           Point to: new row in audit table, compliance panel, expand reasoning chains"
echo ""
echo -e "  ${AMBER}SCENE 5${RESET} — Backtest run (all 4 alerts, auto-approve)"
echo -e "           ${CYAN}python3 backtest.py${RESET}     ← runs all alerts automatically"
echo -e "           Watch: pipeline badge cycle through each stage live"
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

# ── Step 5: Wait for user to finish demo ─────────────────────────────────────
echo ""
echo -e "${AMBER}${BOLD}  ✦  Recording is live. Run your demo now.${RESET}"
echo ""
echo -e "  When you're done, come back here and press ${BOLD}ENTER${RESET} to stop."
read -r

# ── Step 6: Stop recording and save ──────────────────────────────────────────
header "Stopping recording"

osascript <<APPLESCRIPT
tell application "QuickTime Player"
    set docs to every document
    repeat with d in docs
        try
            stop d
            delay 0.5
            -- Save to Desktop
            set theFile to POSIX file "$SAVE_PATH"
            export d to theFile using settings preset "1080p"
        end try
    end repeat
end tell
APPLESCRIPT

sleep 2

# ── Step 7: Cleanup ───────────────────────────────────────────────────────────
header "Cleaning up"
kill "$SERVER_PID" 2>/dev/null || true
ok "Server stopped"

echo ""
echo -e "${GREEN}${BOLD}  ✓ Recording saved to:${RESET}"
echo -e "    $SAVE_PATH"
echo ""
echo -e "  Check ~/Desktop for your demo video."
echo ""
