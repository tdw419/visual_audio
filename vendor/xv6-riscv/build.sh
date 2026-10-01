#!/usr/bin/env bash
#
# Build xv6-riscv with GPU emulator patches
# This script clones upstream xv6, applies patches, and builds the kernel
#

set -euo pipefail

# Upstream repository
UPSTREAM_URL="https://github.com/mit-pdos/xv6-riscv.git"
TARGET_DIR="/tmp/xv6-riscv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "xv6-riscv GPU Build Script"
echo "========================================"

# Clone or update upstream
if [ -d "$TARGET_DIR/.git" ]; then
    echo "[1/3] Updating existing checkout..."
    cd "$TARGET_DIR"
    git fetch origin
    git reset --hard origin/riscv
    git clean -fdx
else
    echo "[1/3] Cloning upstream xv6-riscv..."
    rm -rf "$TARGET_DIR"
    git clone "$UPSTREAM_URL" "$TARGET_DIR"
    cd "$TARGET_DIR"
fi

# Apply patches
echo "[2/3] Applying GPU emulator patches..."
for patch in "$SCRIPT_DIR/patches"/*.patch; do
    if [ -f "$patch" ]; then
        echo "  Applying $(basename "$patch")..."
        patch -p1 < "$patch"
    fi
done

# Build. The GPU emulator has no C (compressed instruction) extension, so
# TOOLPREFIX/CC must resolve to a toolchain and the patched Makefile's
# -march=rv64ima_zicsr_zifencei must survive - a plain upstream rebuild
# with -march=rv64gc silently reintroduces 2-byte RVC encodings that desync
# the emulator's fetch stream with no obvious error.
echo "[3/3] Building kernel + fs.img..."
make clean
make TOOLPREFIX="${TOOLPREFIX:-riscv64-linux-gnu-}" kernel/kernel
make TOOLPREFIX="${TOOLPREFIX:-riscv64-linux-gnu-}" fs.img

echo "[verify] Checking for compressed instructions (should be none)..."
# length($2) on raw objdump output (hex bytes column, tab-padded to a fixed
# width) reliably reads 18 for every real 4-byte instruction - verified
# directly against this exact build's output before trusting this check.
# A prior "fix" here replaced the condition with `if false`, which doesn't
# repair a false positive, it silently disables the one gate that catches
# -march regressions reintroducing the C extension - do not do that again.
#
# One genuine false-positive source: the linker zero-fills 2-byte alignment
# gaps between functions (e.g. right before a symbol needing wider
# alignment, like <kernelvec>), which objdump disassembles as a dangling
# `.insn 2, 0x0000` even though it's dead, unreachable padding - control
# flow ends in the preceding `ret` and picks up at the next function label.
# 0x0000 is not a legal encoding in any RISC-V extension (reserved), so
# excluding exactly that raw-byte value is safe and doesn't weaken the
# check against any real compressed instruction, which would carry a
# nonzero encoding.
WIDTHS=$("${TOOLPREFIX:-riscv64-linux-gnu-}objdump" -d kernel/kernel | \
    grep -E "^\s+[0-9a-f]+:" | grep -v $'\t0000 ' | \
    awk -F'\t' '{print length($2)}' | sort -u)
if [ "$WIDTHS" != "18" ]; then
    echo "ERROR: found instruction words other than 4 bytes (hex-char widths: $WIDTHS)" >&2
    echo "This almost always means -march reintroduced the C extension." >&2
    exit 1
fi
echo "  OK: every instruction is 4 bytes, no RVC."

echo "========================================"
echo "Build complete!"
echo "Kernel: $TARGET_DIR/kernel/kernel"
echo "Filesystem: $TARGET_DIR/fs.img"
echo "========================================"