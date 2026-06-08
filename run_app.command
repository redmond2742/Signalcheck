#!/bin/bash
# Double-click this file (or run it in Terminal) to start the 4-Way Flash Checker.
# It serves on all network interfaces so other computers on the LAN can connect.

cd "$(dirname "$0")" || exit 1

PORT=8501
PY=".env/bin/streamlit"
[ -x "$PY" ] || PY=".venv_xls/bin/streamlit"   # fall back to the other venv
[ -x "$PY" ] || PY="streamlit"                  # or whatever is on PATH

# Show the address(es) other computers should use.
echo "Starting 4-Way Flash Checker..."
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
if [ -n "$IP" ]; then
  echo "On other computers, open:  http://$IP:$PORT"
fi
echo "On this computer, open:    http://localhost:$PORT"
echo "Press Ctrl+C to stop."
echo

exec "$PY" run flash_app.py --server.address 0.0.0.0 --server.port "$PORT"
