# Pixel VM Monitoring & Driver Optimization System

A comprehensive system for monitoring virtio pixel driver performance from inside the pixel-booted VM and generating specific optimization recommendations for the virtio_pixel_rs_v2 backend.

## Overview

This system provides two-way optimization:

1. **VM-side Monitoring** (`vm_pixel_monitor.py`): Runs inside the guest VM to capture real-time I/O patterns
2. **Backend Optimization** (`pixel_driver_optimizer.py`): Analyzes monitoring data and generates specific code changes for the virtio pixel driver v2

## Components

### 1. VM Pixel Monitor (`tools/vm_pixel_monitor.py`)

Runs inside the pixel-booted Ubuntu guest VM to monitor block device I/O patterns.

**Features:**
- Real-time block device monitoring using blktrace or /proc/diskstats
- Sequential vs random access pattern detection
- Hot sector identification and tracking
- I/O burst detection and analysis
- I/O amplification factor calculation
- Throughput and latency monitoring
- JSON output for backend analysis

**Usage inside the VM:**
```bash
# Basic monitoring for 60 seconds
python3 tools/vm_pixel_monitor.py --duration 60 --output /tmp/pixel_analysis.json

# Real-time monitoring with live statistics
python3 tools/vm_pixel_monitor.py --duration 120 --realtime --output /tmp/pixel_realtime.json

# Analyze existing results
python3 tools/vm_pixel_monitor.py --analyze --output /tmp/pixel_analysis.json
```

**Output:**
```json
{
  "io_statistics": {
    "total_reads": 12500,
    "total_writes": 8300,
    "read_throughput_mbps": 45.2,
    "write_throughput_mbps": 12.8
  },
  "pattern_analysis": {
    "sequential_reads": 10500,
    "random_reads": 2000,
    "hot_sectors_count": 450,
    "io_amplification_factor": 2.3
  },
  "optimization_recommendations": [...]
}
```

### 2. Pixel Driver Optimizer (`tools/pixel_driver_optimizer.py`)

Analyzes VM monitoring results and generates specific optimization recommendations for the virtio_pixel_rs_v2 backend.

**Features:**
- Pattern-based optimization suggestion generation
- Backend code analysis and patch generation
- ROI-based implementation prioritization
- Specific code changes with location markers
- Expected performance improvements

**Usage:**
```bash
# Analyze VM monitoring results and generate optimizations
python3 tools/pixel_driver_optimizer.py --input /tmp/pixel_analysis.json --output /tmp/optimizations.json

# Generate code patches for optimizations
python3 tools/pixel_driver_optimizer.py --input /tmp/pixel_analysis.json --patches --output /tmp/optimizations.json

# Suggest general backend improvements (without monitoring data)
python3 tools/pixel_driver_optimizer.py --suggest --backend systems/virtio_pixel_rs_v2/src/
```

**Output:**
```json
{
  "monitoring_summary": {...},
  "optimizations": [
    {
      "file": "backend.rs",
      "title": "Add sequential pattern detection and prefetch",
      "priority": "high",
      "difficulty": "moderate",
      "code_changes": [...],
      "expected_improvement": "2-3x sequential read performance"
    }
  ],
  "implementation_priority": [
    "backend.rs::Add sequential pattern detection (ROI: 3.3)",
    "lib.rs::Implement hot sector caching (ROI: 2.5)"
  ]
}
```

## Monitoring Metrics

### I/O Statistics
- **Total reads/writes**: Number of block operations
- **Throughput**: MB/s for reads and writes  
- **Unique sectors**: Number of distinct sectors accessed
- **Average I/O size**: Mean size of read/write operations

### Pattern Analysis
- **Sequential vs random**: Ratio of sequential to random accesses
- **Hot sectors**: Frequently accessed sectors (defined by threshold)
- **Cold sectors**: Rarely accessed sectors
- **I/O bursts**: Temporally clustered operations
- **I/O amplification**: Actual vs optimal I/O operations ratio

### Optimization Recommendations

Generated based on detected patterns:

1. **High sequential ratio (>70%)**: Prefetch and readahead optimizations
2. **High random ratio (>70%)**: Cache policy optimizations
3. **Many hot sectors (>100)**: Tiered caching implementation
4. **Read bursts detected**: Batch I/O optimizations
5. **High I/O amplification (>2x)**: Write coalescing and combining

## Backend File Optimization Targets

### `backend.rs` (VirtioPixelServer)
- Sequential pattern detection in `poll_virtqueue()`
- Request coalescing for burst patterns
- Write buffer and flush interval optimization
- Virtqueue batching improvements

### `lib.rs` (SpatialMkvExtractor)  
- Hot sector tracking and tiered caching
- LRU cache eviction policy
- Frame cache optimization
- Prefetch method implementation

### `wgpu_texture_loader.rs`
- Batch texture loading
- GPU memory pooling
- Async texture upload pipeline
- Large read optimizations

### `cow_journal.rs`
- Write coalescing for reduced amplification
- Journal compression optimization
- COW delta journal improvements

## Typical Workflow

### 1. Monitor VM Performance
```bash
# Inside the guest VM
python3 /host_zion/projects/visual_audio/tools/vm_pixel_monitor.py --duration 60 --output /tmp/pixel_boot_analysis.json
```

### 2. Generate Optimizations
```bash
# On the host
python3 tools/pixel_driver_optimizer.py --input /tmp/pixel_boot_analysis.json --output /tmp/optimizations.json --patches
```

### 3. Apply Optimizations
```bash
# Review generated patches
ls -la /tmp/patches/

# Apply patches manually or with automated tools
cd systems/virtio_pixel_rs_v2/src/
# Apply changes suggested in patches
```

### 4. Test and Verify
```bash
# Rebuild backend with optimizations
cd systems/virtio_pixel_rs_v2
cargo build --release

# Monitor performance improvements
python3 tools/vm_pixel_monitor.py --duration 60 --output /tmp/pixel_optimized.json

# Compare results
python3 tools/pixel_driver_optimizer.py --analyze --output /tmp/pixel_optimized.json
```

## Integration with Pixel Boot

### Automatic Monitoring Setup
Add to `pixel_ubuntu.sh`:
```bash
# Start VM monitoring in background
MONITOR_OUTPUT="/tmp/pixel_boot_$(date +%Y%m%d_%H%M%S).json"
python3 /host_zion/projects/visual_audio/tools/vm_pixel_monitor.py --duration 300 --output "$MONITOR_OUTPUT" &
MONITOR_PID=$!

# ... VM boot code ...

# Cleanup monitoring
kill $MONITOR_PID 2>/dev/null
echo "VM monitoring results saved to $MONITOR_OUTPUT"
```

### Host-side Analysis
After VM shutdown:
```bash
# Analyze the monitoring results
python3 tools/pixel_driver_optimizer.py --input "$MONITOR_OUTPUT" --output /tmp/optimizations.json --patches

# Review and apply optimizations
```

## Expected Performance Improvements

Based on typical pixel boot patterns:

- **Sequential reads**: 2-3x improvement with readahead
- **Hot sector access**: 5-10x improvement with tiered caching
- **Burst I/O**: 40-60% improvement with request coalescing
- **I/O amplification**: 2-4x reduction with write combining
- **Overall boot time**: 30-50% reduction with combined optimizations

## Troubleshooting

### blktrace not available
The monitor falls back to `/proc/diskstats` monitoring with lower granularity:
```bash
# Install blktrace for better monitoring
sudo apt-get install blktrace
```

### No monitoring data captured
Ensure the VM is performing I/O operations:
```bash
# Generate test I/O patterns
dd if=/dev/zero of=/tmp/test.img bs=1M count=100
dd if=/tmp/test.img of=/dev/null bs=1M count=100
```

### Optimizations don't match code
The optimizer assumes standard backend structure. Customize code_change templates for your specific implementation.

## Advanced Usage

### Custom monitoring duration
```bash
# Monitor for specific workload phases
python3 tools/vm_pixel_monitor.py --duration 30 --output /tmp/kernel_boot.json
python3 tools/vm_pixel_monitor.py --duration 60 --output /tmp/systemd_startup.json
python3 tools/vm_pixel_monitor.py --duration 120 --output /tmp/desktop_load.json
```

### Combined optimization analysis
```bash
# Merge multiple monitoring results
python3 -c "
import json
results = []
for f in ['/tmp/kernel_boot.json', '/tmp/systemd_startup.json', '/tmp/desktop_load.json']:
    results.append(json.load(open(f)))

# Combine statistics
combined = {
    'io_statistics': {
        'total_reads': sum(r['io_statistics']['total_reads'] for r in results),
        'total_writes': sum(r['io_statistics']['total_writes'] for r in results)
    },
    # ... combine other fields
}
print(json.dumps(combined, indent=2))
" > /tmp/combined_monitoring.json
```

### Backend-specific optimization
```bash
# Analyze specific backend files
python3 tools/pixel_driver_optimizer.py --suggest --backend systems/virtio_pixel_rs_v2/src/backend.rs
```

## Contributing to Driver Improvements

When implementing optimizations:

1. **Apply in Git worktree** (per AGENTS.md):
```bash
git worktree add ../pixel-driver-optimizations -b pixel-driver-optimizations
cd ../pixel-driver-optimizations
```

2. **Test optimization impact**:
```bash
# Run monitoring before changes
python3 tools/vm_pixel_monitor.py --duration 60 --output /tmp/before.json

# Apply optimization changes

# Run monitoring after changes
python3 tools/vm_pixel_monitor.py --duration 60 --output /tmp/after.json

# Compare results
python3 tools/pixel_driver_optimizer.py --input /tmp/after.json
```

3. **Pass verification gates**:
```bash
# Ensure optimizations don't break existing functionality
python3 tools/vm_pixel_monitor.py --analyze --output /tmp/verification.json
```

4. **Merge back** only after successful testing.

## Documentation and Skills

For more information on pixel driver architecture and optimization techniques:

- See `AGENTS.md` for pixel driver design constraints
- See `PXC1_IMPLEMENTATION_SUMMARY.md` for COW journal details
- See `PIXEL_BOOT_PERSISTENCE.md` for persistence mechanisms
- Consider creating a skill for pixel driver optimization workflows if this becomes a recurring task.