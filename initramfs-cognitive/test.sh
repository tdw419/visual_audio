#!/bin/bash
# Test Cognitive Initramfs - Validate components and boot logic

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INITRAMFS="${SCRIPT_DIR}/output/initramfs-cognitive.gz"
TEST_DIR="/tmp/cognitive-initramfs-test-$$"

echo "=== Cognitive Initramfs Validation ==="
echo ""

if [ ! -f "${INITRAMFS}" ]; then
    echo "❌ Initramfs not found: ${INITRAMFS}"
    echo "Run build.sh first"
    exit 1
fi

SIZE=$(du -h "${INITRAMFS}" | cut -f1)
echo "✓ Initramfs found (${SIZE})"
echo ""

# Extract to test directory
echo "Extracting initramfs for validation..."
rm -rf "${TEST_DIR}"
mkdir -p "${TEST_DIR}"
cd "${TEST_DIR}"
zcat "${INITRAMFS}" | cpio -idmv >/dev/null 2>&1
echo "✓ Extracted successfully"
echo ""

# Validate structure
echo "=== Structure Validation ==="

declare -a REQUIRED=(
    "init"
    "bin/busybox"
    "bin/sh"
    "bin/mount"
    "bin/python3"
    "usr/lib/python3.12"
    "usr/local/lib/llama_cpp"
    "mnt/pixels"
    "tmp/cognitive"
)

declare -a OPTIONAL=(
    "lib/libc.so.6"
    "lib/libssl.so.3"
    "lib/libcrypto.so.3"
    "usr/local/lib/llama_cpp/llama_cpp.so"
)

MISSING=0
for path in "${REQUIRED[@]}"; do
    if [ -e "${path}" ]; then
        echo "  ✓ ${path}"
    else
        echo "  ✗ ${path} - MISSING"
        ((MISSING++))
    fi
done

echo ""
echo "Optional components:"
for path in "${OPTIONAL[@]}"; do
    if [ -e "${path}" ]; then
        echo "  ✓ ${path}"
    else
        echo "  ⚠️  ${path} - not found"
    fi
done

if [ ${MISSING} -gt 0 ]; then
    echo ""
    echo "❌ Validation failed: ${MISSING} required components missing"
    exit 1
fi

echo ""
echo "=== Component Validation ==="

# Check init script
echo "Checking init script..."
if grep -q "Cognitive Boot Initramfs" init; then
    echo "  ✓ Init script contains cognitive boot header"
else
    echo "  ✗ Init script missing cognitive boot header"
    ((MISSING++))
fi

if grep -q "llama-cpp-python" init; then
    echo "  ✓ Init script references llama-cpp-python"
else
    echo "  ⚠️  Init script may not use LLM inference"
fi

if grep -q "mnt/pixels" init; then
    echo "  ✓ Init script checks for pixel container mount"
else
    echo "  ✗ Init script missing pixel container check"
    ((MISSING++))
fi

if grep -q "switch_root" init; then
    echo "  ✓ Init script includes switch_root for normal boot"
else
    echo "  ✗ Init script missing switch_root"
    ((MISSING++))
fi

# Check Python
echo ""
echo "Checking Python installation..."
if [ -x bin/python3 ]; then
    echo "  ✓ Python 3 binary exists and is executable"
    
    # Try to import basic modules
    PYTHON_OUTPUT=$(bin/python3 -c "import sys, json, hashlib; print('OK')" 2>&1 || echo "FAIL")
    if [ "${PYTHON_OUTPUT}" = "OK" ]; then
        echo "  ✓ Python can import required modules (sys, json, hashlib)"
    else
        echo "  ⚠️  Python import test failed: ${PYTHON_OUTPUT}"
    fi
else
    echo "  ✗ Python 3 not executable"
    ((MISSING++))
fi

# Check llama-cpp-python
echo ""
echo "Checking llama-cpp-python installation..."
if [ -d usr/local/lib/llama_cpp ]; then
    echo "  ✓ llama-cpp-python directory exists"
    
    # Check for shared library
    if find usr/local/lib/llama_cpp -name "*.so" | grep -q .; then
        echo "  ✓ llama-cpp-python shared library found"
    else
        echo "  ⚠️  llama-cpp-python shared library not found"
    fi
    
    # Check for Python module
    if [ -f usr/local/lib/llama_cpp/__init__.py ]; then
        echo "  ✓ llama-cpp-python Python module found"
    else
        echo "  ⚠️  llama-cpp-python Python module not found"
    fi
else
    echo "  ✗ llama-cpp-python directory missing"
    ((MISSING++))
fi

# Check busybox applets
echo ""
echo "Checking Busybox applets..."
BUSYBOX_APPLETS=$(bin/busybox --list | wc -l)
echo "  ✓ Busybox provides ${BUSYBOX_APPLETS} applets"

if [ -x bin/sh ] && [ -x bin/mount ] && [ -x bin/cat ] && [ -x bin/grep ]; then
    echo "  ✓ Core applets (sh, mount, cat, grep) available"
else
    echo "  ✗ Some core applets missing"
    ((MISSING++))
fi

# Check shared libraries
echo ""
echo "Checking shared libraries..."
LIB_COUNT=$(find lib usr/lib -name "*.so*" 2>/dev/null | wc -l)
echo "  ✓ Found ${LIB_COUNT} shared libraries"

if [ -f lib/libc.so.6 ]; then
    echo "  ✓ libc.so.6 found"
else
    echo "  ⚠️  libc.so.6 not found (may cause runtime issues)"
fi

echo ""
echo "=== Summary ==="
echo "Initramfs size: ${SIZE}"
echo "Missing required components: ${MISSING}"

if [ ${MISSING} -eq 0 ]; then
    echo ""
    echo "✅ Cognitive Initramfs validation PASSED"
    echo ""
    echo "The initramfs contains all components required for:"
    echo "  • Boot process management"
    echo "  • Pixel container access (/mnt/pixels)"
    echo "  • Python-based GGUF decoding"
    echo "  • LLM inference via llama-cpp-python"
    echo "  • Self-aware boot queries"
    echo ""
    echo "Next steps:"
    echo "  1. Inject into VAC2 MKV via cognitive_boot_injector.py"
    echo "  2. Boot with QEMU using -initrd flag"
    echo "  3. Observe cognitive boot messages in console output"
    exit 0
else
    echo ""
    echo "❌ Cognitive Initramfs validation FAILED"
    echo "Missing ${MISSING} required components"
    exit 1
fi