#!/bin/bash
#
# multi_pixel_boot.sh - Boot multiple pixel Linux instances
#
# Usage:
#   ./multi_pixel_boot.sh <num_instances> [instance_start]
#
# instance_start defaults to 1, since instance 0 (port 2222) collides with
# the port used by interactive_ubuntu_pixel.sh's dev-mode session.

set -eo pipefail

NUM_INSTANCES="${1:-2}"
INSTANCE_START="${2:-1}"
CONTAINER_DIR="ubuntu_desktop_pxc1_v1"
SECTION="rootfs"

echo "=== Multi-Instance Pixel Linux Boot ==="
echo "Instances: ${NUM_INSTANCES}"
echo "Container: ${CONTAINER_DIR}"
echo "Section: ${SECTION}"
echo

# Export master raw image first (reused for all instances)
MASTER_RAW="/tmp/pixel_boot_master/${SECTION}.raw"
mkdir -p "/tmp/pixel_boot_master"

if [ ! -f "${MASTER_RAW}" ] || [ "${CONTAINER_DIR}" -nt "${MASTER_RAW}" ]; then
    echo "Exporting master raw image..."
    python3 tools/pxc1_raw_export.py "${CONTAINER_DIR}" "${SECTION}" "${MASTER_RAW}"
    echo "✓ Master export complete"
else
    echo "✓ Using existing master export"
fi

# Start instances
echo
echo "Starting instances..."
pids=()

for i in $(seq $INSTANCE_START $((INSTANCE_START + NUM_INSTANCES - 1))); do
    echo "Starting instance ${i}..."

    # Create symlink to master for instance 0
    mkdir -p "/tmp/pixel_boot_${i}"
    ln -sf "${MASTER_RAW}" "/tmp/pixel_boot_${i}/${SECTION}.raw"

    # Start in background, capture PID. Pass the real container dir (not the
    # per-instance scratch dir) so pxc1_raw_export.py finds header.json if it
    # ever needs to export for real; the pre-seeded symlink above means the
    # "already exists" check in pixel_boot.sh skips re-export here.
    ./pixel_boot.sh "${CONTAINER_DIR}" "${SECTION}" "${i}" --delay > "/tmp/pixel_boot_${i}/boot.log" 2>&1 &
    pids+=($!)
done

echo
echo "All ${NUM_INSTANCES} instances started"
echo "PIDs: ${pids[@]}"
echo
echo "Monitoring boot progress (30s)..."
sleep 30

# Check status
echo
echo "=== Boot Status ==="
for i in $(seq $INSTANCE_START $((INSTANCE_START + NUM_INSTANCES - 1))); do
    log_file="/tmp/pixel_boot_${i}/boot.log"
    
    if [ -f "${log_file}" ]; then
        if grep -q "ubuntu login:" "${log_file}"; then
            echo "Instance ${i}: ✓ Booted to login prompt"
        elif grep -q "kernel panic" "${log_file}"; then
            echo "Instance ${i}: ✗ Kernel panic"
        elif grep -q "Failed to get" "${log_file}"; then
            echo "Instance ${i}: ✗ Lock contention"
        else
            echo "Instance ${i}: ? Still booting"
        fi
    else
        echo "Instance ${i}: ! No log file"
    fi
done

echo
echo "=== SSH Ports ==="
for i in $(seq $INSTANCE_START $((INSTANCE_START + NUM_INSTANCES - 1))); do
    port=$((2222 + i * 2))
    if timeout 1 bash -c "echo '' | nc -z localhost ${port}" 2>/dev/null; then
        echo "Instance ${i} (port ${port}): OPEN ✓"
    else
        echo "Instance ${i} (port ${port}): CLOSED ✗"
    fi
done

echo
echo "Instances running. Press Ctrl+C to stop all."
echo "To connect to instance N: ssh -p \$((2222 + N * 2)) jericho@localhost"
echo

# Wait for Ctrl+C
trap 'echo "Stopping all instances..."; kill ${pids[@]} 2>/dev/null; wait; echo "All stopped."; exit 0' INT

# Keep alive monitoring
while true; do
    sleep 10
    
    # Check if any instance died
    dead=0
    idx=0
    for i in $(seq $INSTANCE_START $((INSTANCE_START + NUM_INSTANCES - 1))); do
        log_file="/tmp/pixel_boot_${i}/boot.log"
        if [ -f "${log_file}" ]; then
            if ! grep -q "ubuntu login:" "${log_file}"; then
                # Check if process still running
                if ! ps -p ${pids[$idx]} > /dev/null 2>&1; then
                    echo "Instance ${i} died unexpectedly"
                    dead=1
                fi
            fi
        fi
        idx=$((idx + 1))
    done
    
    if [ ${dead} -eq 1 ]; then
        echo "One or more instances died, stopping all..."
        kill ${pids[@]} 2>/dev/null
        wait
        break
    fi
done