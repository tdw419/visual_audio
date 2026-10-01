#!/bin/bash
# Demo: Trace simple Linux commands to extract pixel programs
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"

echo "=== Pixel Program Extraction Demo ==="
echo ""
echo "This demo traces several Linux commands to understand"
echo "how they are encoded as pixel operations."
echo ""

mkdir -p "$PROJECT_ROOT/pixel_traces"

# Command 1: Simple echo
echo "Command 1: Tracing 'echo Hello, World!'"
echo "---"
pixel_trace_command.sh echo "Hello, World!"
echo ""

# Command 2: List directory
echo "Command 2: Tracing 'ls /etc'"
echo "---"
pixel_trace_command.sh ls /etc | head -20
echo ""

# Command 3: Read file
echo "Command 3: Tracing 'cat /etc/hostname'"
echo "---"
pixel_trace_command.sh cat /etc/hostname
echo ""

# Command 4: Complex command
echo "Command 4: Tracing 'find /etc -name passwd'"
echo "---"
pixel_trace_command.sh find /etc -name passwd
echo ""

echo "=== Demo Complete ==="
echo ""
echo "Trace files saved to: $PROJECT_ROOT/pixel_traces/"
echo ""
echo "To analyze any trace:"
echo "  analyze_pixel_trace.sh <session_id>"
echo ""
echo "Example:"
echo "  analyze_pixel_trace.sh \$(ls -t $PROJECT_ROOT/pixel_traces/*.json | head -1 | xargs basename -s .json)"
echo ""
