# Alpine Boot Verification Script — GPU RV64 Emulator
#
# Run pre-boot and boot-time verification for Alpine Linux on GPU RV64 emulators.
#
# Usage:
#   ./references/alpine_boot_verification.sh [options]
#
# Options:
#   --dtb-path PATH    Path to DTB file (default: auto-detect from kernel path)
#   --kernel-path PATH  Path to kernel image (default: auto-detect)
#   --skip-pre         Skip pre-boot verification, only run boot-time checks
#   --verbose         Show detailed output
#
# This script should be run BEFORE and AFTER booting Alpine to detect regressions.

set -e

# Default paths (can be overridden)
DTB_PATH=""
KERNEL_PATH="boot_images/alpine_riscv64.lnx.bin"
BOOT_LOG="/tmp/alpine_boot.log"
SKIP_PRE=false
VERBOSE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dtb-path)
            DTB_PATH="$2"
            shift 2
            ;;
        --kernel-path)
            KERNEL_PATH="$2"
            shift 2
            ;;
        --skip-pre)
            SKIP_PRE=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=== Alpine Boot Verification ==="

if [ "$VERBOSE" = true ]; then
    echo "DTB path: ${DTB_PATH:-auto-detect from kernel path}"
    echo "Kernel path: $KERNEL_PATH"
    echo "Boot log: $BOOT_LOG"
    echo "Skip pre-boot: $SKIP_PRE"
fi

# ============================================================================
# Pre-Boot Verification
# ============================================================================

if [ "$SKIP_PRE" = false ]; then
    echo ""
    echo "[1] Pre-Boot Verification"

    # 1. Verify DTB structure
    echo "  [1a] Checking DTB well-formedness..."
    if [ ! -f "$DTB_PATH" ]; then
        if [ -f "$KERNEL_PATH" ]; then
            # Derive DTB path from kernel path
            DTB_PATH="${KERNEL_PATH%.lnx.bin}_gpu_machine.dtb"
        fi
        if [ ! -f "$DTB_PATH" ]; then
            echo "  ✗ DTB not found: $DTB_PATH"
            exit 1
        fi
    fi

    if command -v dtc >/dev/null 2>&1; then
        DTB_OUTPUT=$(mktemp)
        dtc -I "$DTB_PATH" -O dts > "$DTB_OUTPUT" || {
            echo "  ✗ dtc failed to parse DTB"
            rm -f "$DTB_OUTPUT"
            exit 1
        }

        # Count virtio nodes
        VIRTIO_COUNT=$(grep -c "virtio_mmio@10007000" "$DTB_OUTPUT" || echo "0")
        if [ "$VIRTIO_COUNT" -eq 1 ]; then
            echo "  ✓ DTB well-formed (single virtio node)"
        else
            echo "  ✗ DTB malformed: $VIRTIO_COUNT virtio nodes (expected 1)"
            if [ "$VERBOSE" = true ]; then
                echo "     Run: dtc -I $DTB_PATH -O dts | grep virtio"
            fi
            rm -f "$DTB_OUTPUT"
            exit 1
        fi
        rm -f "$DTB_OUTPUT"
    else
        echo "  ⚠ dtc not available, skipping DTB structure check"
    fi

    # 2. Check kernel image integrity
    echo "  [1b] Checking kernel image integrity..."
    if [ ! -f "$KERNEL_PATH" ]; then
        echo "  ✗ Kernel not found: $KERNEL_PATH"
        exit 1
    fi

    FILE_TYPE=$(file "$KERNEL_PATH")
    case "$FILE_TYPE" in
        *"ELF 64-bit"*"RISC-V"*)
            echo "  ✓ Kernel is RISC-V 64-bit ELF: $FILE_TYPE"
            ;;
        *)
            echo "  ✗ Unexpected kernel format: $FILE_TYPE"
            exit 1
            ;;
    esac

    # 3. Verify OpenSBI available
    echo "  [1c] Checking OpenSBI availability..."
    OPENSBI_PATH="/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin"
    if [ -f "$OPENSBI_PATH" ]; then
        echo "  ✓ OpenSBI firmware found: $OPENSBI_PATH"
    else
        echo "  ✗ OpenSBI firmware not found: $OPENSBI_PATH"
        exit 1
    fi

    echo "  ✓ Pre-boot verification complete"
fi

# ============================================================================
# Boot-Time Verification (requires boot log)
# ============================================================================

if [ ! -f "$BOOT_LOG" ]; then
    echo ""
    echo "[2] Boot-Time Verification"
    echo "  ⚠ Boot log not found: $BOOT_LOG"
    echo "  → Run boot with: python3 tools/boot_alpine_gpu_fixed.py --max-steps 500000000 --batch 5000000 2>&1 | tee $BOOT_LOG"
    exit 1
fi

echo ""
echo "[2] Boot-Time Verification"

# 2a. Check for kernel banner
if grep -q "Linux version" "$BOOT_LOG"; then
    KERNEL_VER=$(grep "Linux version" "$BOOT_LOG" | head -1 | sed 's/.*Linux version //' | sed 's/ .*//')
    echo "  ✓ Kernel banner: $KERNEL_VER"
else
    echo "  ✗ No kernel banner found"
    exit 1
fi

# 2b. Check for VFS panic
if grep -q "Kernel panic" "$BOOT_LOG"; then
    echo "  ✗ Kernel panic detected:"
    grep "Kernel panic" "$BOOT_LOG" | tail -1
    echo ""
    echo "  Checking for virtio probe..."
    if grep -E "(virtio_mmio|virtio_block)" "$BOOT_LOG"; then
        echo "  ✓ Virtio driver probed (panic is unrelated)"
    else
        echo "  ✗ Virtio driver never probed (DTB issue?)"
        echo ""
        echo "  Suggested debugging:"
        echo "    1. Add to bootargs: loglevel=8 virtio_mmio.debug"
        echo "    2. Check DTB node: dtc -I dtb -O dts | grep virtio"
        echo "    3. Check WGSL shader MMIO range: 0x10007000-0x10007200"
    fi
    exit 1
elif grep -q "Run /init" "$BOOT_LOG"; then
    echo "  ✓ 'Run /init' reached — init phase started"
else
    echo "  ✗ Neither panic nor shell prompt — check boot log tail"
    echo ""
    echo "  Last 10 lines of boot log:"
    tail -10 "$BOOT_LOG"
    exit 1
fi

# 2c. Check for UART output exhaustion
UART_LINES=$(wc -l < "$BOOT_LOG" 2>/dev/null || echo "0")
if [ "$UART_LINES" -lt 50 ]; then
    echo "  ⚠ Very short boot log ($UART_LINES lines) — may indicate UART bottleneck"
    echo "  Suggested: Increase UART buffer size or read more frequently"
else
    echo "  ✓ Boot log has $UART_LINES lines — reasonable output"
fi

echo ""
echo "=== Verification Complete ==="
echo "Alpine boot appears healthy. Use boot log for detailed debugging."