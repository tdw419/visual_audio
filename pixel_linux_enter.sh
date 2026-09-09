#!/bin/bash
# pixel_linux_enter.sh — switch this V5 guest from its normal Ubuntu desktop
# into raw-KMS/evdev "pixel Linux" mode: stops gdm (the desktop's DRM
# master) and launches v5_interactive, which mode-sets /dev/dri/card1
# directly and reads the mouse from /dev/input/event2 via an exclusive
# grab(). No X11/Wayland/compositor in the path once this is running.
#
# This WILL evict the live desktop (screen goes black, GDM's session ends)
# — that's DRM's single-master model, not a bug. Run pixel_linux_exit.sh to
# restore the desktop.
set -e

cd "$(dirname "$0")"

BIN="systems/target/debug/examples/v5_interactive"
if [ ! -x "$BIN" ]; then
    echo "error: $BIN not found/executable — build it first:"
    echo "  cd systems && cargo build -p geos_pixel_v5 --example v5_interactive --features gpu,evdev"
    exit 1
fi

echo "Stopping gdm (this will end the current desktop session)..."
sudo systemctl stop gdm

echo "Launching v5_interactive (V5_DRI_CARD=/dev/dri/card1 V5_INPUT_DEVICE=/dev/input/event2)..."
sudo bash -c "nohup env V5_DRI_CARD=/dev/dri/card1 V5_INPUT_DEVICE=/dev/input/event2 '$(pwd)/$BIN' > /tmp/pixel_linux.log 2>&1 & echo \$! > /tmp/pixel_linux.pid"

sleep 1
PID=$(cat /tmp/pixel_linux.pid 2>/dev/null || echo "?")
echo "pixel Linux running, pid $PID, log: /tmp/pixel_linux.log"
echo "Run ./pixel_linux_exit.sh to restore the desktop."
