#!/bin/bash
# run_v5_instrumented.sh — build instrumented v5_interactive, push to guest,
# kill any old instance, and launch with stdout to a log file.
set -e
cd /home/jericho/projects/zion/projects/visual_audio/systems

echo "==> Building instrumented v5_interactive"
cargo build -p geos_pixel_v5 --example v5_interactive --features geos_pixel_v5/gpu,geos_pixel_v5/evdev 2>&1 | tail -3

BIN=target/debug/examples/v5_interactive
SSH="sshpass -p israel ssh -p 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1"
SCP="sshpass -p israel scp -P 2222 -o StrictHostKeyChecking=no"

echo "==> Killing old instance (root-owned)"
$SSH 'echo israel | sudo -S pkill -9 -x v5_interactive; sleep 1; echo done'

echo "==> Pushing binary"
$SCP "$BIN" jericho@127.0.0.1:/tmp/v5_interactive_instr

echo "==> Launching with log"
$SSH 'echo israel | sudo -S bash -c "cp /tmp/v5_interactive_instr /opt/geos_pixel_v5/v5_interactive && chmod +x /opt/geos_pixel_v5/v5_interactive && nohup env V5_DRI_CARD=/dev/dri/card1 V5_INPUT_DEVICE=/dev/input/event2 /opt/geos_pixel_v5/v5_interactive > /tmp/v5_instr.log 2>&1 &"; sleep 3; tail -20 /tmp/v5_instr.log'
