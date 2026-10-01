#!/bin/bash
set -e

# Build v5_kms on host
cd /home/jericho/projects/zion/projects/visual_audio/systems
cargo build --release -p geos_pixel_v5 --example v5_kms --features gpu

# Deploy to VM (SSH port 2222, password: israel)
scp -P 2222 target/release/examples/v5_kms root@localhost:/tmp/

# Run inside VM with diagnostics
ssh -p 2222 root@localhost << 'EOF'
systemctl stop gdm3 2>/dev/null || true
echo "=== Running v5_kms diagnostics ==="
/tmp/v5_kms
echo "=== v5_kms exited, restarting gdm ==="
systemctl start gdm3
EOF
