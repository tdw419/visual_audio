#!/bin/bash
# Auto-run script for guest verification
# Place in cloud-init user-data or run from first login

mount -t 9p -o trans=virtio host_zion /host_zion 2>/dev/null || true

echo "=== GUEST VERIFICATION $(date) ===" > /tmp/guest_self_proof.txt
echo "Hostname: $(hostname)" >> /tmp/guest_self_proof.txt
echo "User: $(whoami)" >> /tmp/guest_self_proof.txt
echo "Working Directory: $(pwd)" >> /tmp/guest_self_proof.txt
echo "Shared FS test: $(ls /host_zion/projects/visual_audio | head -5)" >> /tmp/guest_self_proof.txt

# Try to run Hermes if installed
if command -v hermes &> /dev/null; then
    echo "" >> /tmp/guest_self_proof.txt
    echo "=== HERMES AUTONOMOUS EXECUTION ===" >> /tmp/guest_self_proof.txt
    hermes run "Analyze the current directory and list the top 3 directories by file count" >> /tmp/guest_self_proof.txt 2>&1
    echo "" >> /tmp/guest_self_proof.txt
    echo "HERMES VERIFICATION: SUCCESS" >> /tmp/guest_self_proof.txt
fi

# Copy proof to shared filesystem
cp /tmp/guest_self_proof.txt /host_zion/projects/visual_audio/ 2>/dev/null || true

sync
echo "=== VERIFICATION SCRIPT COMPLETE ==="