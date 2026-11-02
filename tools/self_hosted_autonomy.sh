#!/bin/bash
# self_hosted_autonomy.sh - Fully self-contained autonomous governance demo
# This script runs entirely inside a container that contains all needed tools

set -e

CONTAINER="visual_audio.mkv"
CACHE_DIR="$HOME/.va_run_cache"

echo "=== Self-Contained Autonomous Governance Demo ==="
echo "This demo runs entirely from tools stored inside $CONTAINER"
echo ""

# Step 1: Verify bootstrap tool exists
echo "Step 1: Verifying bootstrap entry..."
python3 tools/va_container.py ls "$CONTAINER" | grep -q "bootstrap/va_container.py" || {
    echo "ERROR: Bootstrap entry not found"
    exit 1
}
echo "✓ Bootstrap entry present"
echo ""

# Step 2: Run autonomous explorer (expands terrain)
echo "Step 2: Running autonomous terrain explorer..."
python3 tools/va_container.py run "$CONTAINER" tools/pixel_explorer_agent.py
echo "✓ Explorer complete"
echo ""

# Step 3: Run city planner (places structures)
echo "Step 3: Running city planner (places biome-appropriate structures)..."
python3 tools/va_container.py run "$CONTAINER" tools/city_planner_agent.py
echo "✓ City planning complete"
echo ""

# Step 4: Run spatial governor (coordinates structures)
echo "Step 4: Running spatial governor (issues governance directives)..."
python3 tools/va_container.py run "$CONTAINER" tools/spatial_governor.py
echo "✓ Governance complete"
echo ""

# Step 5: Show final state
echo "Step 5: Final container state..."
echo "Total entries:"
python3 tools/va_container.py ls "$CONTAINER" | head -1
echo ""
echo "Architecture entries:"
python3 tools/va_container.py ls "$CONTAINER" | grep "\[architecture\]"
echo ""
echo "Governance entries:"
python3 tools/va_container.py ls "$CONTAINER" | grep "\[governance\]"
echo ""
echo "Terrain tiles:"
python3 tools/va_container.py ls "$CONTAINER" | grep "\[terrain_tile\]"
echo ""
echo "=== Demo Complete ==="
echo "All autonomous agents ran from tools stored inside the container."
echo "No external files were required beyond the container itself."