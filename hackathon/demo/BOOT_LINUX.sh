#!/usr/bin/env bash
# BOOT_LINUX.sh — one command: boot Alpine Linux on the GPU core, get a shell.
#
#   ./hackathon/demo/BOOT_LINUX.sh
#
# Builds the shell container on first run (~10s), boots unattended
# (~75 min on the emulated GPU core — the serial console streams live),
# then hands you the prompt. Try: ls /    cat note.txt    free
set -e
cd "$(dirname "$0")/../.."

PY=python3
[ -x venv/bin/python ] && PY=venv/bin/python

BLOB=/tmp/h12/alpine_shell.lnx.bin
if [ ! -f "$BLOB" ]; then
    echo "[boot] building shell container (one-time, ~10 seconds)..."
    "$PY" tools/build_gpu_shell_blob.py -o "$BLOB"
fi

echo "[boot] booting Alpine Linux (RISC-V) on the GPU core."
echo "[boot] this takes a while and needs no input - the serial"
echo "[boot] console streams live below."
echo "[boot] when 'gpu-rv64:~#' appears, it is your prompt. Try: ls /"
echo

# Use the discrete GPU when available (default adapter is often the iGPU).
export GPU_POWER=high

SNAP=/tmp/h12/shell_prompt_snapshot.npz
if [ -f "$SNAP" ]; then
    echo "[boot] found a saved at-prompt machine state - resuming in seconds."
    echo "[boot] (delete $SNAP to force a full boot)"
    exec "$PY" tools/gpu_shell_live.py --kernel "$BLOB" --snapshot "$SNAP" \
        --max-steps "${BOOT_MAX_STEPS:-2500000000}"
fi

exec "$PY" tools/gpu_shell_live.py --kernel "$BLOB" \
    --save-snapshot "$SNAP" \
    --max-steps "${BOOT_MAX_STEPS:-2500000000}"
