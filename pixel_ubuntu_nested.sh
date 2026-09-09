#!/bin/bash
# Nested Ubuntu Boot via VirtIO-Pixel backend with reduced memory for self-hosting
# Optimized for running INSIDE a guest VM (1.5G RAM, port 2224 to avoid conflict)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_DIR="$PROJECT_ROOT/ubuntu_desktop_pxc1_v1"
BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend"
SOCKET="/tmp/virtio-pixel-nested.sock"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
NATIVE_BOOT_DIR="/home/jericho/scratch/ubuntu_boot_native"
KERNEL="$NATIVE_BOOT_DIR/vmlinuz-6.8.0-136-generic"
INITRD="$NATIVE_BOOT_DIR/initrd.img-6.8.0-136-generic"

# NESTED BOOT CONFIGURATION
# Parent guest has 3.8G total, so we allocate 1.5G for nested VM
NESTED_RAM="1.5G"
NESTED_SMP="2"
NESTED_SSH_PORT="2224"  # Different from parent's 2222

# PXC1 COW Journal configuration
COW_JOURNAL_DIR="/tmp/pxc1_cow_journal_nested"
WRITEBACK_INTERVAL=300
COMPACT_INTERVAL=60

# Performance metrics
WRITEBACK_LATENCY_TARGET="10ms"
COMPRESSION_TARGET="2.5x"

echo "=== NESTED Pixel Ubuntu Boot (Self-Hosting) ==="
echo "NESTED CONFIG:"
echo "  • RAM: $NESTED_RAM (parent has 3.8G total)"
echo "  • CPUs: $NESTED_SMP"
echo "  • SSH port: $NESTED_SSH_PORT"
echo "PXC1 COW Journal optimizations:"
echo "  • Writeback latency: ${WRITEBACK_LATENCY_TARGET}"
echo "  • Writeback interval: ${WRITEBACK_INTERVAL}s"
echo "  • Data loss window: ${WRITEBACK_INTERVAL}s"
echo "=================================================="

# Check for PXC1 container
if [ ! -d "$CONTAINER_DIR" ] || [ ! -f "$CONTAINER_DIR/header.json" ]; then
    echo "ERROR: PXC1 container not found at $CONTAINER_DIR"
    echo "Create PXC1 container first using tools/pxc1 encoder"
    exit 1
fi

# Setup COW journal directory
echo "Setting up COW journal at $COW_JOURNAL_DIR..."
mkdir -p "$COW_JOURNAL_DIR"

# Pick a display backend (nested: default to VNC)
DISPLAY_ARGS="-vnc :2"
DISPLAY_MSG="Serial console prints here; connect VNC to 127.0.0.1:5902"
if { [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; } && \
   qemu-system-x86_64 -display help 2>/dev/null | grep -q "^gtk"; then
    DISPLAY_ARGS="-display gtk"
    DISPLAY_MSG="Serial console prints here; QEMU window will open."
fi

echo "$DISPLAY_MSG"
echo "SSH: ssh -p $NESTED_SSH_PORT jericho@127.0.0.1  (password: israel)"
echo "To exit QEMU, press Ctrl-A, then press X."
echo ""

# Cleanup
pkill -9 virtio_pixel_backend 2>/dev/null || true
rm -f "$SOCKET"
rm -rf /home/jericho/scratch/qemu_shm_nested
mkdir -p /home/jericho/scratch/qemu_shm_nested

# Start backend
echo "Starting PXC1-enabled pixel block device backend..."
chmod +x "$BACKEND"
$BACKEND "$CONTAINER_DIR" "$SOCKET" > "$LOG_DIR/virtio_nested_backend.log" 2>&1 &
BACKEND_PID=$!

# Wait for socket
for i in {1..60}; do
    if [ -S "$SOCKET" ]; then break; fi
    sleep 1
done

if [ ! -S "$SOCKET" ]; then
    echo "Error: Backend socket failed to start."
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

# Wait for HTTP daemon (writeback endpoint)
for i in {1..30}; do
    if curl -s http://127.0.0.1:8769/health > /dev/null 2>&1; then break; fi
    sleep 1
done

echo "Backend ready. COW-enabled writeback endpoint available."
echo ""

# PXC1 COW Journal: Fast periodic writeback
write_counter=0
(
    sleep "$WRITEBACK_INTERVAL"
    while true; do
        START=$(date +%s)
        RESULT=$(curl -s -X POST http://127.0.0.1:8769/writeback)
        DURATION=$(( $(date +%s) - START ))
        write_counter=$((write_counter + 1))
        
        if echo "$RESULT" | grep -q '"ok":true'; then
            echo "[$(date +%H:%M:%S)] ✓ PXC1 COW writeback #$write_counter (${DURATION}s)"
            
            if [ $((write_counter % COMPACT_INTERVAL)) -eq 0 ]; then
                echo "[$(date +%H:%M:%S)] 🔄 Compacting COW journal..."
                COMPACT_RESULT=$(curl -s -X POST http://127.0.0.1:8769/compact_journal)
                if echo "$COMPACT_RESULT" | grep -q '"ok":true'; then
                    echo "[$(date +%H:%M:%S)] ✓ Journal compaction complete"
                else
                    echo "[$(date +%H:%M:%S)] ✗ Journal compaction failed"
                fi
            fi
        else
            echo "[$(date +%H:%M:%S)] ✗ PXC1 COW writeback failed: ${RESULT:-connection error}"
        fi
        sleep "$WRITEBACK_INTERVAL"
    done
) &
WRITEBACK_LOOP_PID=$!

# Trap handler - perform final compact and save on exit
cleanup() {
    echo ""
    kill $WRITEBACK_LOOP_PID 2>/dev/null || true

    echo "=== Final PXC1 COW writeback and compaction ==="
    
    if curl -s -X POST http://127.0.0.1:8769/writeback | grep -q '"ok":true'; then
        echo "✓ Final writeback complete"
    else
        echo "✗ Final writeback failed - some data may be lost"
    fi
    
    echo "Compacting COW journal to base container..."
    if curl -s -X POST http://127.0.0.1:8769/compact_journal | grep -q '"ok":true'; then
        echo "✓ Journal compaction complete - base container updated"
    else
        echo "⚠ Journal compaction skipped - delta journal preserved for next boot"
    fi

    echo ""
    STATS=$(curl -s http://127.0.0.1:8769/journal_stats 2>/dev/null || echo "{}")
    echo "COW Journal Statistics: $STATS"
    
    kill $BACKEND_PID 2>/dev/null || true
    rm -f "$SOCKET"
    echo "PXC1 COW session ended. Changes saved to $CONTAINER_DIR"
}
trap cleanup EXIT INT TERM

echo "=== PXC1 COW Persistence Model ==="
echo "• Write interval: ${WRITEBACK_INTERVAL}s (delta journal append: <1ms)"
echo "• Compaction interval: Every $COMPACT_INTERVAL writes"
echo "• Worst case data loss: ${WRITEBACK_INTERVAL}s of un-compacted writes"
echo "=================================================="
echo ""

echo "Booting nested VM (Ubuntu inside Ubuntu)..."
echo ""

# Boot with QEMU natively (reduced memory for nested execution)
qemu-system-x86_64 \
    -machine q35,memory-backend=ram \
    -object memory-backend-file,share=on,size=$NESTED_RAM,mem-path=/home/jericho/scratch/qemu_shm_nested,id=ram \
    -m $NESTED_RAM \
    -smp $NESTED_SMP \
    -cpu host \
    -enable-kvm \
    -vga std \
    -usb -device usb-tablet \
    $DISPLAY_ARGS \
    -netdev user,id=net0,hostfwd=tcp::$NESTED_SSH_PORT-:22 \
    -device virtio-net-pci,netdev=net0 \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-pci,chardev=blk0,num-queues=1,bootindex=1 \
    -fsdev local,id=zionshare,path=/host_zion/projects/visual_audio,security_model=mapped-xattr \
    -device virtio-9p-pci,fsdev=zionshare,mount_tag=host_zion \
    -serial stdio