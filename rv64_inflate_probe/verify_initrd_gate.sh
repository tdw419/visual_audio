#!/usr/bin/env bash
# Verification gate: RV64I Alpine boot initrd integrity (post OpenSBI-FDT-clobber fix).
#
# The initrd must survive to the "Unpacking initramfs" point byte-for-byte.
# Before the fix (initrd at 0x82000000) OpenSBI's FDT relocation to 0x82200000
# corrupted it at +0x200000; after the fix (initrd at 0x82800000) it must match.
#
# Usage: rv64_inflate_probe/verify_initrd_gate.sh   (run from repo root)
set -u
cd "$(dirname "$0")/.." || exit 1

DUMP=rv64_inflate_probe/initrd_gate.bin
TRACE=rv64_inflate_probe/initrd_gate_trace.jsonl
LOG=rv64_inflate_probe/initrd_gate_run.log

echo "=== RV64I initrd integrity gate ==="
echo "[1/3] Booting to 'Unpacking initramfs' and dumping memory..."
python3 tools/monitor_rv64i.py --program alpine \
    --stop-on-uart "Unpacking initramfs" \
    --dump-mem "$DUMP" --out "$TRACE" > "$LOG" 2>&1
rc=$?
if [ $rc -ne 0 ]; then
    echo "FAIL: monitor exited $rc (see $LOG)"
    exit 1
fi

echo "[2/3] Comparing initrd region (phys 0x82800000) against source..."
python3 - "$DUMP" <<'PYEOF'
import sys
from pathlib import Path

dump = Path(sys.argv[1]).read_bytes()
src = Path('rv64_inflate_probe/initrd.gz.bin').read_bytes()
OFF = 0x2800000  # phys 0x82800000 - RAM_BASE 0x80000000
region = dump[OFF:OFF + len(src)]
diffs = sum(1 for i in range(len(src)) if src[i] != region[i])
pct = 100.0 * diffs / len(src)
print(f"  initrd: {diffs:,} diff bytes / {len(src):,} ({pct:.4f}%)")
if diffs == 0:
    print("  PASS: initrd byte-perfect at unpack point")
    sys.exit(0)
# report where the corruption is (helps distinguish regression vs new issue)
first = next((i for i in range(len(src)) if src[i] != region[i]), None)
print(f"  FAIL: first diff at +0x{first:x} (phys 0x{0x82800000 + first:x})")
sys.exit(1)
PYEOF
rc=$?

echo "[3/3] Result: $([ $rc -eq 0 ] && echo PASS || echo FAIL)"
exit $rc
