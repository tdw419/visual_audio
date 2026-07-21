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
    git reset --hard origin/master
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
WIDTHS=$("${TOOLPREFIX:-riscv64-linux-gnu-}objdump" -d kernel/kernel | \
    grep -E "^\s+[0-9a-f]+:" | awk -F'\t' '{print length($2)}' | sort -u)
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