#!/usr/bin/env bash
# Drives the demo inside the "demo" herdr session while vhs records the client.
# Run in the background just before `vhs demo/demo.tape` (record.sh does both).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${DEMO_LOG:-/tmp/herdr-demo-drive.log}"
exec >"$LOG" 2>&1
ts() { echo "[$(date +%M:%S)] $*"; }

# 1. Wait for the demo session to be running, then target its socket.
for i in $(seq 1 60); do
    SOCK=$(herdr session list 2>/dev/null | awk '$1=="demo" && $2=="running" {print $NF}')
    [ -n "${SOCK:-}" ] && break
    sleep 1
done
[ -n "${SOCK:-}" ] || { ts "demo session never appeared"; exit 1; }
export HERDR_SOCKET_PATH="$SOCK"
ts "demo session socket: $SOCK"
sleep 2

hj() { herdr "$@"; }

# Captions are burned into the GIF afterwards (demo/subtitle.py), movie-style,
# below the terminal. Here we only record event timestamps.
EVENTS=/tmp/demo-captions.tsv
: > "$EVENTS"
mark() { printf '%s\t%s\t%s\n' "$(python3 -c 'import time; print(time.time())')" "$1" "$2" >> "$EVENTS"; }
caption() { mark CAP "$1"; ts "caption: $1"; }
keycast() { mark KEY "$1"; ts "keycast: $1"; }

# Arrow keys must be sent as raw CSI bytes; `send-keys right` does not
# reach the Textual app.
DOWN=$'\x1b[B'

P1=$(hj pane list | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['panes'][0]['pane_id'])")
ts "left pane: $P1"

# 2. Layout: split right for the board; clean shell prompts on both panes.
SPLIT=$(hj pane split "$P1" --direction right --ratio 0.5 --no-focus --cwd "$REPO")
P2=$(echo "$SPLIT" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['pane']['pane_id'])")
ts "right pane: $P2"
sleep 1
for P in "$P1" "$P2"; do
    hj pane send-text "$P" "PS1='$ '; clear"
    hj pane send-keys "$P" enter
done
sleep 1

# 3. Right pane: start the board (English UI). This moment is the sync anchor
#    for the subtitle burn-in (the board title bar becomes visible ~1s later).
mark ANCHOR board-start
hj pane send-text "$P2" "LANG=en_US.UTF-8 bin/jira-board"
hj pane send-keys "$P2" enter
sleep 1

# 4. Left pane: start claude and ask it to create a ticket.
hj pane send-text "$P1" "claude"
hj pane send-keys "$P1" enter
# Agent detection takes a few seconds; `agent wait` errors until then.
for attempt in $(seq 1 30); do
    if hj agent wait "$P1" --until idle --timeout 60000; then
        break
    fi
    sleep 2
done
ts "claude is idle; sending request"
caption "1/5  Ask Claude to create a Jira ticket"
sleep 3
REQUEST='Create a Jira task "Add dark mode support" in project KAN and assign it to me. Work silently (no interim commentary), then reply with one short English sentence such as "Created KAN-17". Never mention issue type names or person names.'
for attempt in 1 2 3; do
    if hj agent prompt "$P1" "$REQUEST" --wait --until working --timeout 30000; then
        break
    fi
    ts "prompt attempt $attempt stalled; retrying"
    sleep 3
done
ts "claude is working"
caption "Claude is creating the ticket via the Atlassian integration..."
hj agent wait "$P1" --until idle --timeout 240000
ts "claude finished (ticket should exist)"
sleep 2

# 5. Board: refresh, new card appears.
caption "2/5  Press r to refresh - the new card appears"
sleep 2
keycast "key: r"
hj pane send-keys "$P2" r
ts "board refreshed"
sleep 3

# 6. Drag the new card to In Progress with the mouse (transition picker pops up
#    when several transitions match). Coordinates are derived from the pane text.
caption "3/5  Drag the card with the mouse, Enter runs the Jira transition"
sleep 2
BOARD_TEXT=$(hj pane read "$P2")
COORDS=$(printf '%s' "$BOARD_TEXT" | python3 -c '
import sys
lines = sys.stdin.read().splitlines()
row = next(i + 1 for i, l in enumerate(lines) if "KAN-" in l)
header = next(l for l in lines if "In Progress" in l)
src_x = lines[row - 1].index("KAN-") + 3
dst_x = header.index("In Progress") + 5
print(src_x, row, dst_x)
')
read -r SX SY DX <<<"$COORDS"
ts "drag from ($SX,$SY) to ($DX,$SY)"
keycast "mouse: drag card to In Progress"
hj pane send-text "$P2" "$(printf '\x1b[<0;%d;%dM' "$SX" "$SY")"   # press
sleep 1
hj pane send-text "$P2" "$(printf '\x1b[<32;%d;%dM' $(( (SX+DX)/2 )) "$SY")"  # drag
sleep 1
hj pane send-text "$P2" "$(printf '\x1b[<32;%d;%dM' "$DX" "$SY")"  # drag
sleep 1
hj pane send-text "$P2" "$(printf '\x1b[<0;%d;%dm' "$DX" "$SY")"   # release
sleep 2
keycast "key: Enter (confirm)"
hj pane send-keys "$P2" enter    # confirm -> picker (2 candidates in KAN)
sleep 3
keycast "key: Enter (pick transition)"
hj pane send-keys "$P2" enter    # pick the first transition
ts "transition confirmed"
sleep 4                          # board refreshes itself

# 7. Launch a Claude session from the card (stays on board, badge appears).
caption "4/5  Enter on a card starts a Claude session for it"
sleep 2
keycast "key: Down (focus card)"
hj pane send-text "$P2" "$DOWN"  # re-focus the first card after refresh
sleep 1
keycast "key: Enter (launch session)"
hj pane send-keys "$P2" enter
ts "session launch requested"
# Wait until the launched agent (named kan-*) is actually alive.
for attempt in $(seq 1 45); do
    STATUS=$(hj agent list | python3 -c "
import sys, json
agents = json.load(sys.stdin).get('result', {}).get('agents', [])
print(next((a.get('agent_status') or a.get('status') or '' for a in agents
            if str(a.get('name') or '').startswith('kan-')), ''))
" 2>/dev/null || true)
    ts "launched agent status: ${STATUS:-none}"
    case "$STATUS" in working|idle|blocked|waiting) break ;; esac
    sleep 2
done
sleep 8                          # let the prompt land and the badge poll run
caption "The badge on the card shows the live session status"
keycast "key: r"
hj pane send-keys "$P2" r
sleep 5

# 8. Jump to the session tab (Enter on a card with a running session focuses it).
caption "5/5  Enter again jumps to the session tab"
sleep 2
keycast "key: Down (focus card)"
hj pane send-text "$P2" "$DOWN"  # refresh cleared the focus again
sleep 1
keycast "key: Enter (open the session)"
hj pane send-keys "$P2" enter
ts "focused session tab"
sleep 7

ts "done"
