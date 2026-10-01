#!/bin/bash
# Simple guest verification - write proof to shared filesystem
echo "=== GUEST VM VERIFICATION ===" > /host_zion/projects/visual_audio/guest_proof.txt
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')" >> /host_zion/projects/visual_audio/guest_proof.txt
echo "Hostname: $(hostname)" >> /host_zion/projects/visual_audio/guest_proof.txt
echo "Kernel: $(uname -r)" >> /host_zion/projects/visual_audio/guest_proof.txt
echo "Uptime: $(uptime)" >> /host_zion/projects/visual_audio/guest_proof.txt
echo "Working Directory: $(pwd)" >> /host_zion/projects/visual_audio/guest_proof.txt
echo "=== GUEST SUCCESSFULLY ACCESSED SHARED FILESYSTEM ===" >> /host_zion/projects/visual_audio/guest_proof.txt
echo "Milestone confirmed: Autonomous execution environment inside guest OS" >> /host_zion/projects/visual_audio/guest_proof.txt
sync
echo "[GUEST] Proof written successfully"