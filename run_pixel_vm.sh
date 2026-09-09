#!/bin/bash
# Run a pixel program in the pixel-native VM
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
VM_BUILD="$PROJECT_ROOT/pixel_trace/vm/target/release/pixel_vm"
ANALYSIS_DIR="$PROJECT_ROOT/pixel_traces"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <session_id> [pixel_container_path]"
    echo "Example: $0 trace_1723981234567890"
    echo ""
    echo "This executes a pixel program using the pixel-native VM."
    echo "The program is applied directly to the pixel container."
    echo ""
    exit 1
fi

SESSION_ID="$1"
CONTAINER_PATH="${2:-$PROJECT_ROOT/ubuntu_desktop_pxc1_v1}"

echo "=== Pixel-Native VM Execution ==="
echo "Session ID: $SESSION_ID"
echo "Container: $CONTAINER_PATH"
echo ""

# Check if analysis exists
ANALYSIS_FILE="$ANALYSIS_DIR/analysis_${SESSION_ID}.json"
if [ ! -f "$ANALYSIS_FILE" ]; then
    echo "Error: Analysis not found at $ANALYSIS_FILE"
    echo "Run analyze_pixel_trace.sh $SESSION_ID first"
    exit 1
fi

# Build VM if needed
if [ ! -f "$VM_BUILD" ]; then
    echo "Building pixel VM..."
    cd "$PROJECT_ROOT/pixel_trace"
    cargo build --release
fi

# Run VM
echo "Starting pixel VM..."
echo ""

$VM_BUILD run "$ANALYSIS_FILE" "$CONTAINER_PATH"

echo ""
echo "=== VM Execution Complete ==="
echo ""
echo "Changes were applied to the pixel container."
echo "To see the changes, reboot the Pixel Linux:"
echo "  ./interactive_ubuntu_pixel.sh"
echo ""

exit 0
