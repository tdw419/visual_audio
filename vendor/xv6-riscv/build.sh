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
    echo "[$1] Updating existing checkout..."
    cd "$TARGET_DIR"
    git fetch origin
    git reset --hard origin/master
else
    echo "[$1] Cloning upstream xv6-riscv..."
    rm -rf "$TARGET_DIR"
    git clone "$UPSTREAM_URL" "$TARGET_DIR"
    cd "$TARGET_DIR"
fi

# Apply patches
echo "[$2] Applying GPU emulator patches..."
for patch in "$SCRIPT_DIR/patches"/*.patch; do
    if [ -f "$patch" ]; then
        echo "  Applying $(basename "$patch")..."
        patch -p1 < "$patch"
    fi
done

# Build
echo "[$3] Building kernel..."
make clean
make

echo "========================================"
echo "Build complete!"
echo "Kernel: $TARGET_DIR/kernel/kernel"
echo "========================================"