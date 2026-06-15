#!/usr/bin/env bash
# Launch MeetBuddy as a desktop window (system tray + single window).
# The tray process supervises the backend: it starts the API + capture daemon
# and shows the dashboard in a native window. Linux only.
#
# Usage:  scripts/run-app.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Build the dashboard once if needed (the API serves it).
if [ ! -f "$ROOT/apps/web/out/index.html" ]; then
  echo "Building the dashboard (first run, ~30s)…"
  ( cd "$ROOT/apps/web" && NEXT_PUBLIC_API_URL="" pnpm install && NEXT_PUBLIC_API_URL="" pnpm build )
fi

# The tray runs under system Python (needs pystray/pillow/pywebview); it launches
# the API/daemon under the project venv itself.
if ! PYSTRAY_BACKEND=xorg python3 -c "import pystray, PIL, webview" 2>/dev/null; then
  echo "Missing desktop deps. Install them with:"
  echo "    pip install --user pystray pillow pywebview"
  echo "(cairosvg is optional, for a crisper tray icon.)"
  exit 1
fi

exec python3 "$ROOT/apps/tray/tray.py"
