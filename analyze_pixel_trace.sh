#!/bin/bash
# Analyze a pixel trace to extract pixel program
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
ANALYZER_BUILD="$PROJECT_ROOT/pixel_trace/analyzer/target/release/pixel_analyzer"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <session_id>"
    echo "Example: $0 trace_1723981234567890"
    echo ""
    echo "This analyzes a pixel trace and extracts patterns."
    echo ""
    exit 1
fi

SESSION_ID="$1"

echo "=== Pixel Trace Analysis ==="
echo "Session ID: $SESSION_ID"
echo ""

# Build analyzer if needed
if [ ! -f "$ANALYZER_BUILD" ]; then
    echo "Building pixel analyzer..."
    cd "$PROJECT_ROOT/pixel_trace/analyzer"
    cargo build --release
fi

# Run analysis
echo "Running analysis..."
"$ANALYZER_BUILD" analyze "$SESSION_ID"

echo ""
echo "=== Analysis Complete ==="
echo ""
echo "Results saved to: pixel_traces/analysis_${SESSION_ID}.json"
echo ""

# Display summary
echo "Summary:"
cat "$PROJECT_ROOT/pixel_traces/analysis_${SESSION_ID}.json" | jq -r '.summary'
echo ""

exit 0
