#!/usr/bin/env bash
# Build geos_pixel_v5 v5_interactive_glyph example on the host, push the binary into the running V4 VM, and run it there.
# V5 Phase 3+5 demo: interactive KMS with evdev input + real-time glyph interpreter (window drift)
set -euo pipefail

cd "$(dirname "$0")/systems"

VM_HOST=127.0.0.1
VM_PORT=2222
VM_USER=jericho
VM_PASS=israel
REMOTE_DIR=/opt/geos_pixel_v5

echo "==> Building geos_pixel_v5 v5_interactive_glyph example on host"
cargo build -p geos_pixel_v5 --example v5_interactive_glyph --features gpu,evdev,glyph

BIN=target/debug/examples/v5_interactive_glyph
if [ ! -f "$BIN" ]; then
  echo "error: $BIN not found after build" >&2
  exit 1
fi

SSH="sshpass -p $VM_PASS ssh -p $VM_PORT -o StrictHostKeyChecking=no $VM_USER@$VM_HOST"
SCP="sshpass -p $VM_PASS scp -P $VM_PORT -o StrictHostKeyChecking=no"

echo "==> Ensuring $REMOTE_DIR exists in VM"
$SSH "echo $VM_PASS | sudo -S mkdir -p $REMOTE_DIR && echo $VM_PASS | sudo -S chown $VM_USER:$VM_USER $REMOTE_DIR"

echo "==> Pushing binary"
$SCP "$BIN" "$VM_USER@$VM_HOST:$REMOTE_DIR/v5_interactive_glyph"

if [ "${1:-}" = "--run" ]; then
  echo "==> Stopping gdm (releases DRM master) and running v5_interactive_glyph directly on /dev/dri/card0"
  $SSH "echo $VM_PASS | sudo -S systemctl stop gdm && sleep 1 && echo $VM_PASS | sudo -S $REMOTE_DIR/v5_interactive_glyph; echo $VM_PASS | sudo -S systemctl start gdm"
else
  echo "==> Deployed. Run './deploy_interactive_glyph.sh --run' to stop gdm and execute it, or ssh in manually:"
  echo "    sshpass -p $VM_PASS ssh -p $VM_PORT $VM_USER@$VM_HOST -- $REMOTE_DIR/v5_interactive_glyph"
fi