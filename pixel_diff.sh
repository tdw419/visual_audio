#!/bin/bash
# Visualize the "Pixel Difference" of typing a command
#
# This script forces a writeback, takes a snapshot of the container,
# executes a command (via an injected script), forces another writeback,
# and creates a visual diff showing EXACTLY which pixels changed.
#
# Usage: ./pixel_diff.sh "echo 'Hello World'"

set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
CONTAINER_DIR="$PROJECT_ROOT/ubuntu_desktop_pxc1_v1"
SNAPSHOT_DIR="$PROJECT_ROOT/pixel_snapshots"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

if [ -z "$1" ]; then
    echo -e "${YELLOW}Usage: $0 \"<command to trace>\"${NC}"
    echo -e "${YELLOW}Example: $0 \"echo 'Hello World'\"${NC}"
    echo ""
    echo -e "${GREEN}This will:${NC}"
    echo "  1. Snapshot current container state (PNG)"
    echo "  2. Inject command into guest"
    echo "  3. Execute command"
    echo "  4. Snapshot new state"
    echo "  5. Generate visual diff"
    echo ""
    exit 1
fi

COMMAND="$1"
CMD_SAFE=$(echo "$COMMAND" | sed 's/[^a-zA-Z0-9_-]/_/g' | head -c 20)

echo -e "${GREEN}=== Pixel Difference Visualizer ===${NC}"
echo -e "Command: ${YELLOW}${COMMAND}${NC}"
echo ""

# Ensure snapshot directory exists
mkdir -p "$SNAPSHOT_DIR"

# Function to force writeback via HTTP endpoint
force_writeback() {
    echo -e "${YELLOW}[1/5] Forcing writeback...${NC}"

    # Check if backend is running
    if ! curl -s http://127.0.0.1:8769/health > /dev/null 2>&1; then
        echo -e "${RED}Error: VirtIO Pixel Backend not running on port 8769${NC}"
        echo -e "${RED}Make sure you are running Pixel Linux from another terminal${NC}"
        exit 1
    fi

    RESULT=$(curl -s -X POST http://127.0.0.1:8769/writeback)
    if echo "$RESULT" | grep -q '"ok":true'; then
        echo -e "${GREEN}✓ Writeback successful${NC}"
    else
        echo -e "${RED}✗ Writeback failed: ${RESULT}${NC}"
        exit 1
    fi
}

# Function to capture snapshot of container
capture_snapshot() {
    local snapshot_name="$1"

    echo -e "${YELLOW}[2/5] Capturing snapshot: ${snapshot_name}...${NC}"

    # Create snapshot directory
    local snap_path="$SNAPSHOT_DIR/${snapshot_name}"
    mkdir -p "$snap_path"

    # Copy relevant .rts files (these are the pixel containers)
    # system.rts is usually the filesystem
    if [ -f "$CONTAINER_DIR/system.rts" ]; then
        cp "$CONTAINER_DIR/system.rts" "$snap_path/"
        echo -e "${GREEN}✓ Copied system.rts (${snapshot_name})${NC}"
    else
        echo -e "${RED}Error: system.rts not found in $CONTAINER_DIR${NC}"
        exit 1
    fi

    # Capture metadata
    cat > "$snap_path/metadata.txt" << EOF
Timestamp: $(date)
Command: ${COMMAND}
Snapshot Name: ${snapshot_name}
File Size: $(stat -f%z "$CONTAINER_DIR/system.rts" 2>/dev/null || stat -c%s "$CONTAINER_DIR/system.rts")
MD5: $(md5sum "$CONTAINER_DIR/system.rts" | cut -d' ' -f1)
EOF
}

# Function to inject and execute command
execute_command() {
    echo -e "${YELLOW}[3/5] Injecting command into guest...${NC}"

    # We inject the command by SSHing into the guest
    # Note: This requires the Pixel Linux to be running and accessible via SSH
    # If SSH is not set up, the user needs to run this manually inside the VM

    # Create a script on the host to transfer
    SCRIPT_PATH="/tmp/pixel_diff_script_${TIMESTAMP}.sh"
    cat > "$SCRIPT_PATH" << EOF
#!/bin/bash
# Pixel Diff Command Execution
echo "=== Executing Pixel Diff Command ==="
echo "Command: ${COMMAND}"
echo "Timestamp: \$(date)"
echo ""

# Execute the command
${COMMAND}

EXIT_CODE=\$?
echo ""
echo "=== Command Execution Complete ==="
echo "Exit Code: \$EXIT_CODE"
EOF

    chmod +x "$SCRIPT_PATH"

    echo -e "${GREEN}✓ Script created: ${SCRIPT_PATH}${NC}"
    echo -e "${YELLOW}Attempting to transfer to guest via SSH...${NC}"

    # Try to connect to the guest (default SSH port forwarding in interactive script is 2222)
    if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -p 2222 jericho@127.0.0.1 "echo 'Connected to guest'" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Guest SSH connection established${NC}"

        # Transfer script
        scp -P 2222 -o StrictHostKeyChecking=no "$SCRIPT_PATH" jericho@127.0.0.1:/tmp/

        # Execute script
        ssh -P 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1 "bash /tmp/pixel_diff_script_${TIMESTAMP}.sh"

        echo -e "${GREEN}✓ Command executed on guest${NC}"
    else
        echo -e "${RED}✗ Cannot connect to guest SSH${NC}"
        echo -e "${YELLOW}Please manually run this inside the Pixel Linux guest:${NC}"
        echo ""
        cat "$SCRIPT_PATH"
        echo ""
        echo -e "${YELLOW}Press Enter when done...${NC}"
        read
    fi

    # Cleanup
    rm -f "$SCRIPT_PATH"
}

# Function to generate visual diff
generate_diff() {
    local before="$1"
    local after="$2"

    echo -e "${YELLOW}[4/5] Generating visual diff...${NC}"

    local before_file="$SNAPSHOT_DIR/${before}/system.rts"
    local after_file="$SNAPSHOT_DIR/${after}/system.rts"
    local diff_output="$SNAPSHOT_DIR/${after}/diff.png"

    if [ ! -f "$before_file" ] || [ ! -f "$after_file" ]; then
        echo -e "${RED}Error: Snapshot files missing${NC}"
        exit 1
    fi

    # Check if ImageMagick is available
    if ! command -v compare &> /dev/null; then
        echo -e "${YELLOW}ImageMagick 'compare' not found. Installing...${NC}"
        sudo apt-get update -qq && sudo apt-get install -y imagemagick
    fi

    # Use ImageMagick compare to highlight differences
    # Composition: Difference - highlights changed pixels in red/pink
    echo "Comparing: $before vs $after"

    compare "$before_file" "$after_file" -compose src -highlight-color red -lowlight-color black "$diff_output" 2>/dev/null

    if [ -f "$diff_output" ]; then
        echo -e "${GREEN}✓ Visual diff generated: ${diff_output}${NC}"

        # Also generate a metrics report
        local metrics_output="$SNAPSHOT_DIR/${after}/metrics.txt"
        {
            echo "Pixel Diff Metrics"
            echo "=================="
            echo "Command: ${COMMAND}"
            echo "Before: ${before}"
            echo "After: ${after}"
            echo ""
            # Get pixel stats (requires ImageMagick identify)
            identify -verbose "$diff_output" 2>/dev/null | grep -E "(Statistics|Mean|Standard)" || echo "Detailed stats unavailable"
            echo ""
            # Count changed pixels (rough estimate via unique colors)
            CHANGED_COUNT=$(convert "$diff_output" -define histogram:unique-colors=true -format "%c" histogram:info:- 2>/dev/null | wc -l)
            echo "Estimated unique colors (rough change indicator): $CHANGED_COUNT"
        } > "$metrics_output"

        echo -e "${GREEN}✓ Metrics saved: ${metrics_output}${NC}"
    else
        echo -e "${RED}✗ Failed to generate visual diff${NC}"
        exit 1
    fi
}

# Function to show results
show_results() {
    local snapshot_name="$1"

    echo -e "${GREEN}[5/5] Analysis Complete ===${NC}"
    echo ""
    echo -e "Snapshot directory: ${YELLOW}${SNAPSHOT_DIR}/${snapshot_name}/${NC}"
    echo ""
    echo "Files created:"
    ls -lh "$SNAPSHOT_DIR/${snapshot_name}/"
    echo ""
    echo -e "To view the diff:"
    echo -e "  open ${SNAPSHOT_DIR}/${snapshot_name}/diff.png"
    echo ""
    echo -e "To view the metrics:"
    echo -e "  cat ${SNAPSHOT_DIR}/${snapshot_name}/metrics.txt"
    echo ""
}

# --- Main Execution Flow ---

echo -e "${GREEN}Starting Pixel Diff Workflow...${NC}"
echo ""

# Step 1: Before snapshot
echo -e "${YELLOW}--- Phase 1: Baseline Snapshot ---${NC}"
force_writeback
BEFORE_SNAP="before_${TIMESTAMP}"
capture_snapshot "$BEFORE_SNAP"
echo ""

# Step 2: Execute command
echo -e "${YELLOW}--- Phase 2: Command Execution ---${NC}"
execute_command
echo ""

# Step 3: After snapshot
echo -e "${YELLOW}--- Phase 3: Post-Execution Snapshot ---${NC}"
# Give a moment for any async writes to settle
sleep 1
force_writeback
AFTER_SNAP="after_${CMD_SAFE}_${TIMESTAMP}"
capture_snapshot "$AFTER_SNAP"
echo ""

# Step 4: Generate diff
echo -e "${YELLOW}--- Phase 4: Diff Generation ---${NC}"
generate_diff "$BEFORE_SNAP" "$AFTER_SNAP"
echo ""

# Step 5: Show results
show_results "$AFTER_SNAP"