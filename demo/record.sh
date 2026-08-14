#!/usr/bin/env bash
# Record the README demo GIF: starts the driver, then vhs.
set -euo pipefail
cd "$(dirname "$0")/.."

# Clean slate for the demo session.
herdr session stop demo >/dev/null 2>&1 || true
herdr session delete demo >/dev/null 2>&1 || true

# Hide the user's global CLAUDE.md during the recording so the launched
# sessions answer in plain English. Restored on exit no matter what.
GLOBAL_MD="$HOME/.claude/CLAUDE.md"
if [ -f "$GLOBAL_MD" ]; then
    mv "$GLOBAL_MD" "$GLOBAL_MD.demo-bak"
    trap 'mv "$GLOBAL_MD.demo-bak" "$GLOBAL_MD" 2>/dev/null || true' EXIT
fi

DEMO_LOG=/tmp/herdr-demo-drive.log ./demo/drive.sh &
DRIVER=$!
vhs demo/demo.tape
wait "$DRIVER" || true
herdr session stop demo >/dev/null 2>&1 || true
echo "driver log: /tmp/herdr-demo-drive.log"
