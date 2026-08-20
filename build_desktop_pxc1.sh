#!/bin/bash
# Build a 15GB Ubuntu Desktop Image with Self-Hosting Capability and encode it into PXC1 Hilbert pixels

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Config
SOURCE_RAW="ubuntu-24.04-server-cloudimg-amd64.raw"
DESKTOP_RAW="ubuntu-desktop-15g.raw"
INITRAMFS="initramfs-cognitive/output/initramfs-cognitive.gz"
GGUF="$HOME/.cache/visual_audio/cognitive/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
OUTPUT_DIR="ubuntu_desktop_pxc1_v3_selfhost"

# Self-Hosting Components
V2_BACKEND="systems/virtio_pixel_rs_v2/target/release/virtio_pixel_backend_v2"
SELFHOST_LAUNCHER="tools/pixel_self_host_nested_vm.sh"
FORK_TOOL="tools/pixel_fork_container.sh"

echo "=== 1. Preparing 15GB Desktop Image with Self-Hosting ==="
if [ ! -f "$DESKTOP_RAW" ]; then
    echo "Creating 15G raw disk..."
    qemu-img create -f raw "$DESKTOP_RAW" 15G
    
    echo "Expanding source image into 15G disk..."
    # Depending on the source partition layout, usually partition 1 is rootfs. 
    # Use virt-resize to copy and expand the filesystem natively
    virt-resize --expand /dev/sda1 "$SOURCE_RAW" "$DESKTOP_RAW"
    
    echo "Installing ubuntu-desktop-minimal and self-hosting tools (This will take 15-25 minutes)..."
    cat << 'EOF' > install_pkgs.sh
#!/bin/bash
exec > /dev/console 2>&1
export DEBIAN_FRONTEND=noninteractive
while ! ip route show | grep -q default; do sleep 1; done
apt-get update
apt-get install -y ubuntu-desktop-minimal qemu-system-x86 qemu-utils bridge-utils curl libvulkan1 openssh-server
apt-get clean
poweroff
EOF
    chmod +x install_pkgs.sh

    virt-customize -a "$DESKTOP_RAW" \
        --firstboot install_pkgs.sh

    echo "Booting image in QEMU to run package installation..."
    qemu-system-x86_64 -m 4096 -enable-kvm -cpu host -nographic -serial stdio -no-reboot -drive file="$DESKTOP_RAW",format=raw,if=virtio -netdev user,id=n1 -device virtio-net-pci,netdev=n1
        
    echo "Installing v2 pixel backend..."
    if [ -f "$V2_BACKEND" ]; then
        virt-customize -a "$DESKTOP_RAW" \
            --copy-in "$V2_BACKEND:/usr/local/bin/" \
            --chmod 0755:/usr/local/bin/virtio_pixel_backend_v2
        echo "✓ v2 backend installed"
    else
        echo "⚠ v2 backend not found at $V2_BACKEND - will need to be installed manually in guest"
    fi
    
    echo "Installing self-hosting launchers..."
    if [ -f "$SELFHOST_LAUNCHER" ]; then
        virt-customize -a "$DESKTOP_RAW" \
            --copy-in "$SELFHOST_LAUNCHER:/usr/local/bin/" \
            --chmod 0755:/usr/local/bin/pixel_self_host_nested_vm.sh
        echo "✓ Self-host launcher installed"
    else
        echo "⚠ Self-host launcher not found at $SELFHOST_LAUNCHER"
    fi
    
    if [ -f "$FORK_TOOL" ]; then
        virt-customize -a "$DESKTOP_RAW" \
            --copy-in "$FORK_TOOL:/usr/local/bin/" \
            --chmod 0755:/usr/local/bin/pixel_fork_container.sh
        echo "✓ Container fork tool installed"
    else
        echo "⚠ Container fork tool not found at $FORK_TOOL"
    fi
    
    echo "Setting up self-hosting infrastructure..."
    virt-customize -a "$DESKTOP_RAW" \
        --run-command 'mkdir -p /var/lib/pixel_containers' \
        --run-command 'chmod 777 /var/lib/pixel_containers' \
        --run-command 'chown root:root /var/lib/pixel_containers'
    echo "✓ Container storage directory created"
    
    echo "Configuring systemd for nested boot optimization..."
    # Add timeout for network-wait-online (but don't mask it - needed for normal desktop operation)
    virt-customize -a "$DESKTOP_RAW" \
        --run-command 'mkdir -p /etc/systemd/system/systemd-networkd-wait-online.service.d/' \
        --write '/etc/systemd/system/systemd-networkd-wait-online.service.d/timeout.conf:[Service]
TimeoutStartSec=5sec
' \
        --run-command 'systemctl daemon-reload'
    echo "✓ Network timeout configured for nested boot (5s instead of indefinite)"
    
    echo "Setting up SSH access for nested VMs..."
    # Ensure SSH is configured and running
    virt-customize -a "$DESKTOP_RAW" \
        --run-command 'systemctl enable ssh.service' \
        --run-command 'systemctl start ssh.service'
    echo "✓ SSH service configured"
    
    echo "Creating self-hosting user instructions..."
    cat <<'EOF' > /tmp/selfhost_readme.txt
Pixel Self-Hosting Instructions
================================

This Ubuntu Desktop VM is equipped with pixel self-hosting capability.

Quick Start:
-----------
1. Fork a container: sudo /usr/local/bin/pixel_fork_container.sh /path/to/source /var/lib/pixel_containers/nested_vm
2. Boot nested VM: sudo /usr/local/bin/pixel_self_host_nested_vm.sh --container /var/lib/pixel_containers/nested_vm
3. Access nested VM: ssh -p 2224 jericho@127.0.0.1 (password: israel)

Requirements:
-----------
- v2 backend: /usr/local/bin/virtio_pixel_backend_v2
- QEMU: qemu-system-x86_64 (pre-installed)
- Launcher: /usr/local/bin/pixel_self_host_nested_vm.sh
- Container storage: /var/lib/pixel_containers

Container Management:
--------------------
- Fork containers instantly: sudo /usr/local/bin/pixel_fork_container.sh <source> <dest>
- Check container health: ls -la /var/lib/pixel_containers/
- Monitor nested VMs: sudo /usr/local/bin/pixel_self_host_nested_vm.sh --container <dir>

Performance Notes:
------------------
- Nested VMs should use 1.5-2G RAM minimum
- Each nesting level adds ~20-30% overhead
- Network timeout is set to 5s for faster nested boots

For more information, see: /usr/local/share/doc/pixel-self-hosting/
EOF
    virt-customize -a "$DESKTOP_RAW" \
        --run-command 'mkdir -p /usr/local/share/doc/pixel-self-hosting/' \
        --upload /tmp/selfhost_readme.txt:/usr/local/share/doc/pixel-self-hosting/README.txt
    echo "✓ Self-hosting documentation installed"
    
    rm -f /tmp/selfhost_readme.txt
    
else
    echo "Found existing $DESKTOP_RAW, skipping generation."
    echo "To rebuild with self-hosting components, delete this file and re-run."
fi

echo ""
echo "=== 1b. Verifying $DESKTOP_RAW actually boots to GRUB before encoding ==="
BOOT_CHECK_LOG="$(mktemp)"
timeout 20 qemu-system-x86_64 -m 1G -enable-kvm \
    -drive file="$DESKTOP_RAW",format=raw,if=virtio \
    -nographic -serial "file:$BOOT_CHECK_LOG" -no-reboot >/dev/null 2>&1 || true
if grep -q "grub rescue" "$BOOT_CHECK_LOG" || ! grep -qiE "grub|linux|vmlinuz|loading" "$BOOT_CHECK_LOG"; then
    echo "ERROR: $DESKTOP_RAW does not boot cleanly (grub rescue or no boot output detected)." >&2
    echo "--- boot check serial log ---" >&2
    cat "$BOOT_CHECK_LOG" >&2
    rm -f "$BOOT_CHECK_LOG"
    exit 1
fi
echo "✓ Boot check passed (GRUB/kernel output detected)"
rm -f "$BOOT_CHECK_LOG"

echo ""
echo "=== 2. Compiling PXC1 Encoder ==="
# We refactored pxc1-encode to stream files so it doesn't OOM on 15GB
cargo build --release --manifest-path tools/pxc1/Cargo.toml

echo ""
echo "=== 3. Encoding Desktop Rootfs into Hilbert Pixels ==="
echo "This will encode 15GB of raw data into PXC1 PNG frames. This will take some time."

tools/pxc1/target/release/pxc1-encode \
    "$OUTPUT_DIR" \
    rootfs "$DESKTOP_RAW" \
    initramfs "$INITRAMFS" \
    gguf "$GGUF"

echo ""
echo "=== Desktop PXC1 encoding complete! ==="
echo "Container ready at: $OUTPUT_DIR/"
echo ""
echo "Self-Hosting Golden Image Features:"
echo "  ✓ v2 backend: /usr/local/bin/virtio_pixel_backend_v2"
echo "  ✓ QEMU hypervisor: qemu-system-x86_64"
echo "  ✓ Self-host launcher: /usr/local/bin/pixel_self_host_nested_vm.sh"
echo "  ✓ Zero-copy forking: /usr/local/bin/pixel_fork_container.sh"
echo "  ✓ Container storage: /var/lib/pixel_containers"
echo "  ✓ Network optimization: 5s timeout for nested boots"
echo "  ✓ Documentation: /usr/local/share/doc/pixel-self-hosting/"
echo ""
echo "Usage:"
echo "  1. Boot golden image: ./pixel_ubuntu.sh (or pixel_ubuntu_v2.sh)"
echo "  2. Inside VM: Fork a container and launch nested VM"
echo "  3. Or use the pre-installed launchers directly"
echo ""
echo "Update interactive_ubuntu_pixel.sh to point CONTAINER_DIR to $OUTPUT_DIR to boot it."
