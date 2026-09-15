#!/usr/bin/env bash
set -uo pipefail

BIN="${1:-./target/release/zzview}"
OS="$(uname -s)"

mkdir -p dist docs
LOG="docs/CI_CAPTURE_LOG.md"

say() { echo "$*" | tee -a "$LOG"; }

printf '# CI capture log\n\n```\n' > "$LOG"

say "== zzview UI capture =="
say "date   : $(date -u)"
say "binary : $BIN"
say "os     : $OS"

finish() {
  printf '```\n' >> "$LOG"
  if [ "$OS" = "Linux" ]; then
    git config user.name "github-actions[bot]" || true
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com" || true
    git add "$LOG" || true
    git commit -m "ci: publish capture log [skip" -m "ci]" || true
    git pull --rebase --autostash origin main || true
    git push origin HEAD:main || say "push failed"
  fi
  exit 0
fi

if [ ! -x "$BIN" ]; then
  say "FAIL: binary missing or not executable"
  finish
fi

say "size   : $(wc -c < "$BIN") bytes"

if [ "$OS" != "Linux" ]; then
  say "SKIP: unattended capture only runs on Linux runners"
  finish
fi

say "-- installing capture tools --"
sudo apt-get update -qq >/dev/null 2>&1 || true
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xvfb imagemagick xdotool tesseract-ocr libegl1 libgl1 libgl1-mesa-dri libxkbcommon-x11-0 >/dev/null 2>&1 || true

export ICED_BACKEND=tiny-skia
export LIBGL_ALWAYS_SOFTWARE=1
export WINIT_UNIX_BACKEND=x11
export DISPLAY=:99
say "renderer: ICED_BACKEND=$ICED_BACKEND"

say "-- starting Xvfb --"
Xvfb :99 -screen 0 1200x800x24 >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
sleep 3

say "-- launching zzview --"
"$BIN" >/tmp/zzview.log 2>&1 &
APP_PID=$!

WID=""
for i in $(seq 1 15); do
  sleep 2
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    say "app exited after ~$((i * 2))s"
    break
  fi
  WID="$(xdotool search --name zzview 2>/dev/null | head -n1)"
  if [ -n "$WID" ]; then
    say "window found after ~$((i * 2))s : id=$WID"
    break
  fi
done

sleep 3

SHOT="dist/zzview-ui-linux-x86_64.png"
if [ -n "$WID" ]; then
  xdotool windowactivate "$WID" 2>/dev/null || true
  sleep 1
  import -window "$WID" "$SHOT" 2>/dev/null || import -window root "$SHOT" 2>/dev/null || true
else
  import -window root "$SHOT" 2>/dev/null || true
fi

if [ -f "$SHOT" ]; then
  say "captured : $(wc -c < "$SHOT") bytes"
  convert "$SHOT" -resize 200% -colorspace gray -normalize /tmp/ocr.png 2>/dev/null || cp "$SHOT" /tmp/ocr.png
  tesseract /tmp/ocr.png stdout 2>/dev/null | sed '/^[[:space:]]*$/d' | head -n 25 | tee -a "$LOG" || true
else
  say "WARN: no screenshot produced"
fi

head -n 40 /tmp/zzview.log 2>/dev/null | tee -a "$LOG" || true

kill "$APP_PID" 2>/dev/null || true
kill "$XVFB_PID" 2>/dev/null || true

say "== capture finished =="
finish
