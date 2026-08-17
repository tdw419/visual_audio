#!/bin/bash
# ai_sandbox.sh - A lightweight, instant, resource-capped namespace for the AI daemon

PROJECT_DIR="/home/jericho/projects/zion/projects/visual_audio/systems/infinite_map_rs"
IPC_SOCKET="/tmp/spatial_compositor.sock"

# We use systemd-run to apply resource limits to the sandbox
# This ensures a runaway rustc compilation doesn't freeze the host OS.
exec systemd-run --scope --user \
  -p CPUQuota=50% \
  -p MemoryMax=2G \
  -- bwrap \
  --unshare-all \
  --share-net \
  --ro-bind /usr /usr \
  --ro-bind /lib /lib \
  --ro-bind /lib64 /lib64 \
  --ro-bind /bin /bin \
  --ro-bind /etc /etc \
  --symlink usr/lib lib \
  --symlink usr/lib64 lib64 \
  --symlink usr/bin bin \
  --symlink usr/sbin sbin \
  --proc /proc \
  --dev /dev \
  --tmpfs /tmp \
  --bind "$PROJECT_DIR" "/workspace" \
  --bind "$IPC_SOCKET" "/tmp/spatial_compositor.sock" \
  --chdir "/workspace" \
  --die-with-parent \
  python3 rustc_daemon.py
