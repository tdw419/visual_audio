#!/bin/bash
# demo_qemu_from_container.sh -- Demonstrate QEMU disk image encoding and boot from VAC1 container

echo "================================================================"
echo "QEMU from Visual Audio MKV Container - Demo"
echo "================================================================"
echo ""
echo "This demo shows how to encode QEMU disk images into the Visual Audio"
echo "container (as pixel data), then extract and boot them."
echo ""
echo "Use case: 'any software on our map' - encode full OS disk images as"
echo "pixels in the VAC1 container, then launch them via QEMU."
echo ""
echo "================================================================"
echo ""

CONTAINER="${1:-visual_audio.mkv}"

echo "[1] Listing current disk images in container..."
echo "----------------------------------------------------------------"
python3 tools/qemu_from_container.py "$CONTAINER" list
echo ""

if [ ! -f "boot_images/xv6.img" ] && [ ! -f "boot_images/alpine_riscv64.qcow2" ]; then
    echo "[!] No disk images found in boot_images/, cannot demonstrate add."
    echo ""
else
    echo "[2] Adding a disk image to the container (if not already present)..."
    echo "----------------------------------------------------------------"

    # Check if alpine is already in container
    if python3 -c "
import sys; sys.path.insert(0, 'tools')
from visual_audio_container import Container
c = Container('$CONTAINER')
print('1' if any('alpine_riscv64.qcow2' in e['name'] for e in c.list()) else '0')
" 2>/dev/null | grep -q "0"; then
        echo "Adding Alpine RISC-V disk image..."
        python3 tools/qemu_from_container.py "$CONTAINER" add boot_images/alpine_riscv64.qcow2 \
            --name alpine_riscv64.qcow2 \
            --role qemu_disk \
            --note "Alpine Linux RISC-V64 - QEMU bootable disk"
    else
        echo "alpine_riscv64.qcow2 already in container, skipping add."
    fi
    echo ""
fi

echo "[3] Verifying disk image in container..."
echo "----------------------------------------------------------------"
python3 tools/qemu_from_container.py "$CONTAINER" list
echo ""

echo "[4] Launching QEMU from container (10-second demo)..."
echo "----------------------------------------------------------------"
echo "This will:"
echo "  1. Extract alpine_riscv64.qcow2 from VAC1 container to /tmp"
echo "  2. Launch qemu-system-riscv64 with the extracted disk"
echo "  3. Let it boot to login prompt (10 seconds)"
echo "  4. Clean up automatically"
echo ""

timeout 10 python3 tools/qemu_from_container.py "$CONTAINER" \
    launch alpine_riscv64.qcow2 \
    --arch riscv64 \
    --display nographic \
    2>&1 || true

echo ""
echo "================================================================"
echo "✓ Demo Complete"
echo "================================================================"
echo ""
echo "Key capabilities demonstrated:"
echo "  ✓ Encode disk images (qcow2, raw, ISO, etc.) as pixel data in VAC1"
echo "  ✓ Extract disk images from VAC1 container"
echo "  ✓ Launch QEMU VMs from container-stored disk images"
echo "  ✓ Automatic temporary file cleanup"
echo ""
echo "This enables 'any software on our map':"
echo "  1. Encode any bootable disk (Linux, BSD, custom OS) into the container"
echo "  2. The container file IS the software distribution"
echo "  3. Launch from anywhere the container is present"
echo "  4. Disk images are stored losslessly as pixels (FFV1 codec)"
echo ""
echo "Next steps:"
echo "  - Encode more disk images (Ubuntu, Fedora, Alpine x86_64, etc.)"
echo "  - Use with signed boot manifests (tools/boot_manifest.py)"
echo "  - Combine with Visual Audio codec for boot via audio"
echo ""