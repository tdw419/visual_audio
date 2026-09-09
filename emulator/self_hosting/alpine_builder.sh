#!/bin/sh
# emulator/self_hosting/alpine_builder.sh
#
# Build WGSL compiler toolchain in Alpine Linux for V2 self-hosting.
#
# Usage: ./alpine_builder.sh
#
# Environment: Alpine Linux (running on v1 emulator)
# Output: naga WGSL compiler at /usr/local/bin/naga

set -e

echo "=== Alpine WGSL Build Toolchain Setup ==="

# Alpine package manager update
echo "[1/4] Updating Alpine repositories..."
apk update

# Install build dependencies
echo "[2/4] Installing build tools..."
apk add --no-cache \
    alpine-sdk \
    musl-dev \
    python3 \
    py3-pip \
    git \
    make \
    curl \
    ca-certificates

# Install Rust and Cargo
echo "[3/4] Installing Rust..."
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
export PATH="$HOME/.cargo/bin:$PATH"
source "$HOME/.cargo/env"

# Build naga WGSL compiler
echo "[4/4] Building naga WGSL compiler..."
cargo install naga-cli --root /usr/local

# Verify installation
if command -v naga >/dev/null 2>&1; then
    naga_version=$(naga --version 2>/dev/null || echo "unknown")
    echo ""
    echo "=== Build Complete ==="
    echo "naga version: $naga_version"
    echo "naga path: $(command -v naga)"
    echo ""
    echo "Test WGSL compilation:"
    echo "  naga compile input.wgsl --output format=spv > output.spv"
    echo ""
else
    echo "ERROR: naga installation failed"
    exit 1
fi

echo "=== Setup Complete ==="
echo "Alpine is ready to compile V2 WGSL shaders"