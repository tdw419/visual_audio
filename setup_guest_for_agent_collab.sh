#!/bin/bash
# Run inside guest to set up Hermes and context bridge
set -e

GUEST_HOME="/home/jericho"
HERMES_DIR="$GUEST_HOME/.hermes"
PROJECT_DIR="/host_zion/projects/hermes-agent"

echo "=== GUEST SETUP FOR AGENT COLLABORATION ==="
echo "Installing Hermes from shared FS..."

# Install Hermes
if [ ! -d "$HERMES_DIR" ]; then
    mkdir -p "$HERMES_DIR"
    cp -r "$PROJECT_DIR" "$HERMES_DIR/hermes-agent"
    cd "$HERMES_DIR/hermes-agent"
    python3 -m venv venv
    source venv/bin/activate
    pip install -e .
else
    echo "Hermes already installed"
fi

# Create context marker directory
mkdir -p /host_zion/projects/visual_audio/.hermes_guest_context

echo "=== GUEST READY ==="
echo "Hermes: $HERMES_DIR/hermes-agent"
echo "Shared FS: /host_zion"
echo "Context: /host_zion/projects/visual_audio/.hermes_guest_context"