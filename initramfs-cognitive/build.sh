#!/bin/bash
# Build Cognitive Initramfs - Create a bootable initramfs with LLM inference capability

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"
INITRAMFS_FILE="${OUTPUT_DIR}/initramfs-cognitive.gz"

echo "=== Building Cognitive Initramfs ==="

# Clean and create output directory
rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"
cd "${OUTPUT_DIR}"

# Create initramfs directory structure
mkdir -p bin lib lib64 usr/lib usr/local/lib sbin dev proc sys tmp etc mnt/pixels tmp/cognitive sysroot

# Copy busybox (minimal userland)
if [ -f /bin/busybox ]; then
    cp /bin/busybox bin/
elif command -v busybox >/dev/null 2>&1; then
    cp "$(command -v busybox)" bin/
else
    echo "❌ busybox not found - please install: sudo apt-get install busybox"
    exit 1
fi

# Install busybox applets
cd bin
for applet in $(./busybox --list); do
    [ "$applet" = "busybox" ] && continue  # Skip self-reference
    ln -sf busybox "$applet"
done
cd "${OUTPUT_DIR}"

# Copy Python3 (required for pixel decoding and LLM inference)
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1-2)
echo "Python version: ${PYTHON_VERSION}"

# Copy python3 binary and essential libraries
cp /usr/bin/python3 bin/

# Copy Python stdlib (minimal subset)
PYTHON_LIB="/usr/lib/python${PYTHON_VERSION}"
if [ -d "${PYTHON_LIB}" ]; then
    mkdir -p usr/lib
    cp -r "${PYTHON_LIB}" usr/lib/
    
    # Remove unnecessary modules to save space
    find usr/lib/python${PYTHON_VERSION} -name "*.pyc" -delete
    find usr/lib/python${PYTHON_VERSION} -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    rm -rf usr/lib/python${PYTHON_VERSION}/test \
           usr/lib/python${PYTHON_VERSION}/distutils/tests \
           usr/lib/python${PYTHON_VERSION}/lib2to3/tests \
           usr/lib/python${PYTHON_VERSION}/tkinter \
           usr/lib/python${PYTHON_VERSION}/idlelib
else
    echo "⚠️  Python stdlib not found at ${PYTHON_LIB}"
fi

# Copy shared libraries required by Python and busybox
echo "Copying shared libraries..."
for lib in \
    libssl.so.3 libcrypto.so.3 \
    libz.so.1 \
    libexpat.so.1 \
    libbz2.so.1 \
    liblzma.so.5 \
    libffi.so.8 \
    libm.so.6 libc.so.6 libdl.so.2 libpthread.so.0 \
    libstdc++.so.6 libgcc_s.so.1
do
    find /lib /usr/lib -name "${lib}" 2>/dev/null | grep -E "(x86_64-linux-gnu|lib64)" | head -1 | while read path; do
        if [ -f "$path" ]; then
            cp "$path" lib/ 2>/dev/null || cp "$path" usr/lib/ 2>/dev/null || true
        fi
    done
done

# Copy typing_extensions for llama-cpp-python
echo "Copying Python typing_extensions..."
TYPING_EXT=$(python3 -c "import typing_extensions; print(typing_extensions.__file__)" 2>/dev/null)
if [ -n "$TYPING_EXT" ]; then
    TYPING_DIR=$(dirname "$TYPING_EXT")
    mkdir -p usr/lib/python${PYTHON_VERSION}/site-packages
    cp "$TYPING_EXT" usr/lib/python${PYTHON_VERSION}/site-packages/
    echo "  ✓ Copied $TYPING_EXT"
fi

# Copy dynamic linker
if [ -f /lib64/ld-linux-x86-64.so.2 ]; then
    cp /lib64/ld-linux-x86-64.so.2 lib64/
fi

# Check for llama-cpp-python installation
echo "Checking for llama-cpp-python..."
if python3 -c "import llama_cpp" 2>/dev/null; then
    LLAMA_CPP_PATH=$(python3 -c "import llama_cpp; import os; print(os.path.dirname(llama_cpp.__file__))")
    echo "✓ llama-cpp-python found at ${LLAMA_CPP_PATH}"
    
    # Copy llama-cpp-python module
    mkdir -p usr/local/lib
    cp -r "${LLAMA_CPP_PATH}" usr/local/lib/
    
    # Find and copy llama.cpp shared library
    for lib in libllama.so libllama.so.*; do
        find /usr/lib /usr/local/lib -name "${lib}" 2>/dev/null | head -1 | while read path; do
            if [ -f "$path" ]; then
                echo "  Copying ${lib}"
                cp "$path" usr/lib/ 2>/dev/null || cp "$path" lib/ 2>/dev/null || true
            fi
        done
    done
else
    echo "⚠️  llama-cpp-python not installed"
    echo "  Install with: pip install llama-cpp-python"
    echo "  Cognitive inference will fail at boot time"
fi

# Copy init script and cognitive extraction tools
cp "${SCRIPT_DIR}/init" init
chmod 755 init
cp "${SCRIPT_DIR}/extract_cognitive.py" bin/
chmod 755 bin/extract_cognitive.py

# Create device nodes (if running as root, skip if permission denied)
(
    mknod -m 666 dev/null c 1 3 2>/dev/null || echo "  (Skipping /dev/null - may exist or need root)"
    mknod -m 666 dev/zero c 1 5 2>/dev/null || true
    mknod -m 666 dev/random c 1 8 2>/dev/null || true
    mknod -m 666 dev/urandom c 1 9 2>/dev/null || true
    mknod -m 600 dev/console c 5 1 2>/dev/null || true
) 2>/dev/null || echo "  (Device nodes will be created at runtime by devtmpfs)"

# Create fstab
cat > etc/fstab << 'EOF'
devfs /dev devfs defaults 0 0
proc /proc proc defaults 0 0
EOF

# Package as gzip-compressed cpio archive
echo ""
echo "Packaging initramfs..."
find . -path "./initramfs-cognitive.gz" -prune -o -print | cpio -H newc -o | gzip -9 > "${INITRAMFS_FILE}"

SIZE=$(du -h "${INITRAMFS_FILE}" | cut -f1)
echo ""
echo "✓ Cognitive Initramfs built successfully"
echo "  Output: ${INITRAMFS_FILE}"
echo "  Size: ${SIZE}"
echo ""
echo "Components included:"
echo "  - Busybox (core userland)"
echo "  - Python 3.${PYTHON_VERSION}"
[ -d "usr/local/lib/llama_cpp" ] && echo "  - llama-cpp-python (LLM inference)" || echo "  ⚠️  llama-cpp-python NOT installed"
echo "  - Pixel decoding logic"
echo "  - Self-aware boot scripts"
echo ""
echo "To use with QEMU:"
echo "  qemu-system-x86_64 \\"
echo "    -kernel vmlinuz \\"
echo "    -initrd ${INITRAMFS_FILE} \\"
echo "    -drive file=disk.img,format=raw,if=virtio \\"
echo "    -m 4096 -smp 4"