#!/usr/bin/env bash
# Bounded Alpine GPU boot smoke — the h1 freeze gate. ~90s wall, no interaction.
# One command, self-sufficient: recreates the verify worktree and the gitignored
# boot_images symlink from the canonical kernel asset (md5-verified) if missing.
#
# NEVER raise BOOT_SMOKE_MAX_STEPS to 1400000000 from a lane: the full 1.4B-step
# boot is a MANUAL DAY-MARKER (~35 min), per HACKATHON_DEMO_PREVERIFY_2026-10-20.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../../.. && pwd)"
KERNEL_SRC="$HOME/zion/apps/linux/alpine/alpine-riscv64.lnx.bin"
KERNEL_MD5="0cad7ccf7111eef3c0bc1e903b947001"   # frozen canonical asset (PREVERIFY receipt)
PY="$REPO_ROOT/venv/bin/python"
WT="${BOOT_SMOKE_WORKTREE:-/home/jericho/tmp/wt_hackathon_verify}"
MAX_STEPS="${BOOT_SMOKE_MAX_STEPS:-20000000}"   # default freeze smoke ~90s
GATE_TIMEOUT="${BOOT_SMOKE_TIMEOUT:-600}"       # hard wall-clock cap on the boot

[ -x "$PY" ] || { echo "FATAL: venv python missing: $PY" >&2; exit 2; }
[ -f "$KERNEL_SRC" ] || { echo "FATAL: canonical kernel asset missing: $KERNEL_SRC" >&2; exit 2; }
GOT_MD5="$(md5sum "$KERNEL_SRC" | cut -d' ' -f1)"
if [ "$GOT_MD5" != "$KERNEL_MD5" ]; then
  echo "FATAL: kernel md5 $GOT_MD5 != frozen $KERNEL_MD5 — refusing to smoke" >&2
  exit 2
fi

if [ ! -f "$WT/tools/boot_alpine_gpu_fixed.py" ]; then
  git -C "$REPO_ROOT" worktree add --detach "$WT" HEAD >&2
fi

# Fresh-checkout pattern (PREVERIFY setup notes): boot_images/ assets are
# gitignored — mkdir + ln -s from the canonical copy.
mkdir -p "$WT/boot_images"
ln -sfn "$KERNEL_SRC" "$WT/boot_images/alpine_riscv64.lnx.bin"

LOG="$(mktemp /tmp/hackathon_boot_smoke.XXXX.log)"
cd "$WT"
# shellcheck disable=SC2086 — timeout is fine unquoted-split here
timeout "$GATE_TIMEOUT" "$PY" tools/boot_alpine_gpu_fixed.py \
  --max-steps "$MAX_STEPS" --batch 5000000 > "$LOG" 2>&1
grep -q "Linux version 6.12.31-0-lts" "$LOG"
grep -q "smp: Brought up 1 node, 1 CPU" "$LOG"
echo "BOOT_SMOKE PASS: kernel banner + SMP up ($LOG)"
