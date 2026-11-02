#!/bin/bash
# Complete Pixel Monitoring and Optimization Workflow
# Run this on the host to coordinate VM monitoring and backend optimization

set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
TOOLS_DIR="$PROJECT_ROOT/tools"
RESULTS_DIR="/tmp/pixel_monitoring"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Pixel Monitoring & Optimization System ===${NC}"
echo -e "${BLUE}Coordinated VM monitoring and backend optimization workflow${NC}"
echo ""

# Check if we're in the right environment
if [ ! -d "$PROJECT_ROOT" ]; then
    echo -e "${RED}Error: Project directory not found: $PROJECT_ROOT${NC}"
    exit 1
fi

# Create results directory
mkdir -p "$RESULTS_DIR"
mkdir -p "$RESULTS_DIR/patches"

echo -e "${GREEN}✓ Environment ready${NC}"
echo "  Project root: $PROJECT_ROOT"
echo "  Results directory: $RESULTS_DIR"
echo ""

# Menu system
echo -e "${YELLOW}Select workflow:${NC}"
echo "1) Monitor VM I/O patterns (run inside VM)"
echo "2) Analyze monitoring results and generate optimizations"
echo "3) Suggest general backend improvements"
echo "4) Full workflow: Monitor → Analyze → Optimize"
echo "5) Show monitoring results summary"
echo ""
read -p "Enter choice [1-5]: " choice

case $choice in
    1)
        # VM Monitoring (inside VM)
        echo -e "${YELLOW}=== VM Monitoring Mode ===${NC}"
        echo "This mode runs inside the guest VM to monitor I/O patterns"
        echo ""
        
        read -p "Monitoring duration (seconds) [60]: " duration
        duration=${duration:-60}
        
        read -p "Output file [${RESULTS_DIR}/vm_monitor_${TIMESTAMP}.json]: " output
        output=${output:-${RESULTS_DIR}/vm_monitor_${TIMESTAMP}.json}
        
        read -p "Enable real-time stats? [y/N]: " realtime
        realtime_flag=""
        [[ "$realtime" =~ ^[Yy]$ ]] && realtime_flag="--realtime"
        
        echo ""
        echo -e "${GREEN}Starting VM monitoring...${NC}"
        echo "  Duration: ${duration}s"
        echo "  Output: $output"
        echo "  Real-time: ${realtime_flag:-disabled}"
        echo ""
        
        # Check if running inside VM
        if [ -d "/host_zion" ]; then
            echo "Detected VM environment. Running monitor..."
            python3 "$TOOLS_DIR/vm_pixel_monitor.py" \
                --duration "$duration" \
                --output "$output" \
                $realtime_flag
            
            echo -e "${GREEN}✓ VM monitoring complete${NC}"
            echo "Results saved to: $output"
        else
            echo -e "${RED}Error: Not running inside a VM${NC}"
            echo "This workflow must be executed inside the pixel-booted guest VM"
            echo ""
            echo "To monitor from outside, use SSH:"
            echo "  ssh -p 2222 jericho@127.0.0.1 'python3 /host_zion/projects/visual_audio/tools/vm_pixel_monitor.py --duration $duration --output $output'"
            exit 1
        fi
        ;;
        
    2)
        # Analyze monitoring results
        echo -e "${YELLOW}=== Monitoring Analysis Mode ===${NC}"
        echo "Analyze VM monitoring results and generate backend optimizations"
        echo ""
        
        read -p "Input monitoring results file: " input_file
        if [ ! -f "$input_file" ]; then
            echo -e "${RED}Error: Input file not found: $input_file${NC}"
            echo "Available monitoring results:"
            ls -la "$RESULTS_DIR"/vm_monitor_*.json 2>/dev/null || echo "  No monitoring results found"
            exit 1
        fi
        
        read -p "Output file [${RESULTS_DIR}/optimizations_${TIMESTAMP}.json]: " output
        output=${output:-${RESULTS_DIR}/optimizations_${TIMESTAMP}.json}
        
        read -p "Generate code patches? [y/N]: " generate_patches
        patches_flag=""
        [[ "$generate_patches" =~ ^[Yy]$ ]] && patches_flag="--patches"
        
        echo ""
        echo -e "${GREEN}Analyzing monitoring results...${NC}"
        echo "  Input: $input_file"
        echo "  Output: $output"
        echo "  Generate patches: ${generate_patches:-no}"
        echo ""
        
        python3 "$TOOLS_DIR/pixel_driver_optimizer.py" \
            --input "$input_file" \
            --output "$output" \
            $patches_flag
        
        echo -e "${GREEN}✓ Analysis complete${NC}"
        echo "Optimization report saved to: $output"
        
        if [[ "$generate_patches" =~ ^[Yy]$ ]]; then
            echo "Code patches saved to: ${RESULTS_DIR}/patches/"
        fi
        
        echo ""
        echo "View results:"
        echo "  cat $output"
        ;;
        
    3)
        # Suggest general improvements
        echo -e "${YELLOW}=== Backend Analysis Mode ===${NC}"
        echo "Analyze backend code and suggest general improvements"
        echo ""
        
        read -p "Backend path [$PROJECT_ROOT/systems/virtio_pixel_rs_v2]: " backend_path
        backend_path=${backend_path:-$PROJECT_ROOT/systems/virtio_pixel_rs_v2}
        
        if [ ! -d "$backend_path" ]; then
            echo -e "${RED}Error: Backend directory not found: $backend_path${NC}"
            exit 1
        fi
        
        read -p "Output file [${RESULTS_DIR}/suggestions_${TIMESTAMP}.json]: " output
        output=${output:-${RESULTS_DIR}/suggestions_${TIMESTAMP}.json}
        
        echo ""
        echo -e "${GREEN}Analyzing backend code...${NC}"
        echo "  Backend: $backend_path"
        echo "  Output: $output"
        echo ""
        
        python3 "$TOOLS_DIR/pixel_driver_optimizer.py" \
            --suggest \
            --backend "$backend_path" \
            --output "$output"
        
        echo -e "${GREEN}✓ Analysis complete${NC}"
        echo "Suggestions saved to: $output"
        ;;
        
    4)
        # Full workflow
        echo -e "${YELLOW}=== Full Optimization Workflow ===${NC}"
        echo "Complete pipeline: Monitor VM → Analyze patterns → Generate optimizations"
        echo ""
        
        # Check if running inside VM
        if [ -d "/host_zion" ]; then
            echo -e "${GREEN}Running in VM mode (inside guest)${NC}"
            
            read -p "Monitoring duration (seconds) [60]: " duration
            duration=${duration:-60}
            
            monitor_output="${RESULTS_DIR}/vm_monitor_${TIMESTAMP}.json"
            
            echo ""
            echo -e "${BLUE}Step 1: Monitoring VM I/O patterns...${NC}"
            python3 "$TOOLS_DIR/vm_pixel_monitor.py" \
                --duration "$duration" \
                --output "$monitor_output" \
                --realtime
            
            echo -e "${GREEN}✓ VM monitoring complete${NC}"
            echo "Results saved to: $monitor_output"
            echo ""
            
            echo -e "${BLUE}Step 2: Generating optimization recommendations...${NC}"
            optimizer_output="${RESULTS_DIR}/optimizations_${TIMESTAMP}.json"
            python3 "$TOOLS_DIR/pixel_driver_optimizer.py" \
                --input "$monitor_output" \
                --output "$optimizer_output" \
                --patches
            
            echo -e "${GREEN}✓ Optimization analysis complete${NC}"
            echo "Report saved to: $optimizer_output"
            echo "Patches saved to: ${RESULTS_DIR}/patches/"
            echo ""
            
            echo -e "${BLUE}Step 3: Summary and next steps...${NC}"
            echo "Monitoring duration: ${duration}s"
            echo "Output files:"
            echo "  Monitoring: $monitor_output"
            echo "  Optimizations: $optimizer_output"
            echo "  Patches: ${RESULTS_DIR}/patches/"
            echo ""
            echo -e "${YELLOW}Next steps:${NC}"
            echo "1. Review optimization recommendations:"
            echo "   cat $optimizer_output"
            echo ""
            echo "2. Apply high-priority optimizations to backend:"
            echo "   cd systems/virtio_pixel_rs_v2/src/"
            echo "   # Review patches in ${RESULTS_DIR}/patches/"
            echo ""
            echo "3. Rebuild and test:"
            echo "   cd systems/virtio_pixel_rs_v2"
            echo "   cargo build --release"
            echo ""
            echo "4. Verify improvements:"
            echo "   # Run monitoring again with optimized backend"
            echo "   python3 /host_zion/projects/visual_audio/tools/vm_pixel_monitor.py --duration $duration --output ${RESULTS_DIR}/optimized_monitor_${TIMESTAMP}.json"
            
        else
            echo -e "${YELLOW}Running in host mode${NC}"
            echo "Will coordinate VM monitoring via SSH"
            echo ""
            
            read -p "Monitoring duration (seconds) [60]: " duration
            duration=${duration:-60}
            
            read -p "SSH port [2222]: " ssh_port
            ssh_port=${ssh_port:-2222}
            
            read -p "SSH user [jericho]: " ssh_user
            ssh_user=${ssh_user:-jericho}
            
            monitor_output="${RESULTS_DIR}/vm_monitor_${TIMESTAMP}.json"
            
            echo ""
            echo -e "${BLUE}Step 1: Monitoring VM I/O patterns via SSH...${NC}"
            echo "  Connecting to localhost:$ssh_port as $ssh_user"
            echo "  Monitoring duration: ${duration}s"
            echo ""
            
            ssh_cmd="ssh -p $ssh_port ${ssh_user}@127.0.0.1 'python3 /host_zion/projects/visual_audio/tools/vm_pixel_monitor.py --duration $duration --output $monitor_output --realtime'"
            
            echo "Executing: $ssh_cmd"
            eval "$ssh_cmd"
            
            if [ ! -f "$monitor_output" ]; then
                echo -e "${RED}Error: Monitoring results not found: $monitor_output${NC}"
                exit 1
            fi
            
            echo -e "${GREEN}✓ VM monitoring complete${NC}"
            echo "Results saved to: $monitor_output"
            echo ""
            
            echo -e "${BLUE}Step 2: Generating optimization recommendations...${NC}"
            optimizer_output="${RESULTS_DIR}/optimizations_${TIMESTAMP}.json"
            python3 "$TOOLS_DIR/pixel_driver_optimizer.py" \
                --input "$monitor_output" \
                --output "$optimizer_output" \
                --patches
            
            echo -e "${GREEN}✓ Optimization analysis complete${NC}"
            echo "Report saved to: $optimizer_output"
            echo "Patches saved to: ${RESULTS_DIR}/patches/"
            echo ""
            
            echo -e "${BLUE}Step 3: Summary and next steps...${NC}"
            echo "Monitoring duration: ${duration}s"
            echo "Output files:"
            echo "  Monitoring: $monitor_output"
            echo "  Optimizations: $optimizer_output"
            echo "  Patches: ${RESULTS_DIR}/patches/"
            echo ""
            echo -e "${YELLOW}Next steps:${NC}"
            echo "1. Review optimization recommendations:"
            echo "   cat $optimizer_output"
            echo ""
            echo "2. Apply high-priority optimizations to backend:"
            echo "   cd systems/virtio_pixel_rs_v2/src/"
            echo "   # Review patches in ${RESULTS_DIR}/patches/"
            echo ""
            echo "3. Rebuild and test:"
            echo "   cd systems/virtio_pixel_rs_v2"
            echo "   cargo build --release"
            echo ""
            echo "4. Verify improvements:"
            echo "   # Run monitoring again with optimized backend"
            echo "   $0  # Run this script again and select option 1"
        fi
        ;;
        
    5)
        # Show monitoring results
        echo -e "${YELLOW}=== Monitoring Results Summary ===${NC}"
        echo ""
        
        if [ ! "$(ls -A $RESULTS_DIR/vm_monitor_*.json 2>/dev/null)" ]; then
            echo "No monitoring results found in $RESULTS_DIR"
            exit 0
        fi
        
        echo "Available monitoring results:"
        echo ""
        
        for file in $RESULTS_DIR/vm_monitor_*.json; do
            if [ -f "$file" ]; then
                echo "File: $(basename $file)"
                echo "Size: $(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null) bytes"
                echo "Modified: $(stat -f%Sm "$file" 2>/dev/null || stat -c%y "$file" 2>/dev/null)"
                echo ""
                
                # Extract key statistics if possible
                if command -v python3 &> /dev/null; then
                    python3 -c "
import json
try:
    with open('$file') as f:
        data = json.load(f)
    
    stats = data.get('io_statistics', {})
    patterns = data.get('pattern_analysis', {})
    
    print('Statistics:')
    print(f'  Total I/O: {stats.get(\"total_reads\", 0) + stats.get(\"total_writes\", 0):,} operations')
    print(f'  Read throughput: {stats.get(\"read_throughput_mbps\", 0):.2f} MB/s')
    print(f'  Write throughput: {stats.get(\"write_throughput_mbps\", 0):.2f} MB/s')
    print(f'  Hot sectors: {patterns.get(\"hot_sectors_count\", 0):,}')
    print(f'  I/O amplification: {patterns.get(\"io_amplification_factor\", 0):.1f}x')
    print(f'  Optimizations: {len(data.get(\"optimization_recommendations\", []))}')
except Exception as e:
    print(f'Error parsing file: {e}')
"
                fi
                echo "----------------------------------------"
            fi
        done
        ;;
        
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}=== Workflow Complete ===${NC}"
echo "For more information, see: $PROJECT_ROOT/PIXEL_MONITORING_OPTIMIZATION.md"