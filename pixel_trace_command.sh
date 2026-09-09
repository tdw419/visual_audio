#!/bin/bash
# Trace a Linux command to extract its pixel operations
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
TRACER_BUILD="$PROJECT_ROOT/pixel_trace/tracer/target/release/pixel_tracer"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <command>"
    echo "Example: $0 ls /etc"
    echo ""
    echo "This runs the command and traces all pixel operations."
    echo "The trace is saved to pixel_traces/ directory."
    echo ""
    exit 1
fi

COMMAND="$@"
COMMAND_SAFE=$(echo "$COMMAND" | sed 's/[^a-zA-Z0-9_-]/_/g')

echo "=== Pixel Tracing Session ==="
echo "Command: $COMMAND"
echo ""

# Build tracer if needed
if [ ! -f "$TRACER_BUILD" ]; then
    echo "Building pixel tracer..."
    cd "$PROJECT_ROOT/pixel_trace/tracer"
    cargo build --release
fi

# Start tracer
echo "Starting tracer..."
SESSION_ID=$("$TRACER_BUILD" start "$COMMAND")

echo ""
echo "Session ID: $SESSION_ID"
echo "Executing command..."
echo "----------------------------------------"

# Execute the command
eval "$COMMAND"
EXIT_CODE=$?

echo "----------------------------------------"
echo "Command exited with code: $EXIT_CODE"
echo ""

# Stop tracer and save results
echo "Stopping tracer..."
RESULT=$("$TRACER_BUILD" stop "$SESSION_ID")
TRACE_FILE=$(echo "$RESULT" | grep "Trace saved to:" | sed 's/.*saved to: //')

echo ""
echo "=== Trace Complete ==="
echo "Trace file: $TRACE_FILE"
echo ""
echo "To analyze this trace:"
echo "  analyze_pixel_trace.sh $SESSION_ID"
echo ""

exit $EXIT_CODE
