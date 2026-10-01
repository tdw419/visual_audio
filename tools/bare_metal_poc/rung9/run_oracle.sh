#!/usr/bin/env bash
# rung9/run_oracle.sh — TASK_BM901 gate (boot-handoff oracle).
#
# Structure:
#   Phase A (capture): 2 independent legs of the REAL chain
#     (SeaBIOS -> isolinux -> bzImage) in QEMU, GDB-stub stop at the
#     kernel protected-mode entry (code32_start=0x100000, second hit;
#     first hit is isolinux's own trampoline — verified via HdrS at
#     rsi+0x202). Captures per leg: full zeropage (boot_params) 4KB from
#     rsi, cmdline 512B from hdr.cmd_line_ptr, architectural register
#     state.
#   Phase B (differ): legs must be byte-identical (zeropage, cmdline,
#     register text). ANY diff = FAIL.
#   Phase C (non-vacuity RED legs): the differ must FAIL on
#     (redA) a single flipped byte in a captured zeropage, and
#     (redB) a different kernel image captured with the same chain —
#     implemented as: zeropage captured from the QEMU-direct kernel boot
#     of a DIFFERENT bzImage must differ from the oracle in loader-owned
#     fields.
#   Phase D (receipt): sha256 pins of all artifacts; PASS only if all
#     phases green.
#
# Exit 0 = GATE PASS. Any RED leg that does not RED = FAIL.
set -u
cd "$(dirname "$0")"

echo "=== BM901 ORACLE GATE ==="
FAIL=0

# redA's mutant is this run's, not the machine's. HEAD wrote /tmp/oracle_zp_flipped.bin
# and read it back three lines later, and on the real box that name still held the
# output of the ORIGINAL BM901 run: 4096 B stamped 2026-09-18 19:55, differing from the
# tracked oracle_zp_leg0.bin at exactly one byte, 0x228 0x00 -> 0x01 -- the very flip
# this leg is supposed to perform. So a reader here cannot tell its own write from a
# two-day-old one, and because the stale bytes are the correct answer the leg prints
# PASS without noticing (measured: cmp -s over that pair returns rc=1 with nothing
# written this run). Same mktemp + trap shape as run_bm902_diff.sh:28-32.
ZP_FLIP=$(mktemp "${TMPDIR:-/tmp}/oracle_zp_flipped.XXXXXX.bin") || { echo "GATE FAIL: mktemp"; exit 1; }
trap 'rm -f "$ZP_FLIP"' EXIT

# ---------- Phase A: capture x2 ----------
python3 probe34_capture.py || { echo "GATE FAIL: capture phase errored"; exit 1; }

[ -f oracle_zp_leg0.bin ] && [ -f oracle_zp_leg1.bin ] || { echo "GATE FAIL: dumps missing"; exit 1; }
[ -f oracle_cmdline_leg0.bin ] && [ -f oracle_cmdline_leg1.bin ] || { echo "GATE FAIL: cmdline dumps missing"; exit 1; }

# sanity: zeropage must carry the boot protocol signature
python3 - <<'EOF' || { echo "GATE FAIL: zeropage signature"; exit 1; }
import struct
zp = open('oracle_zp_leg0.bin','rb').read()
assert len(zp) == 4096
assert zp[0x1fe:0x200] == b'\x55\xaa', 'boot flag'
assert zp[0x202:0x206] == b'HdrS', 'HdrS'
assert zp[0x210] == 0x33 or zp[0x210] != 0, 'type_of_loader nonzero (isolinux chainloader)'
EOF

# ---------- Phase B: x2 byte-identical ----------
if cmp -s oracle_zp_leg0.bin oracle_zp_leg1.bin && \
   cmp -s oracle_cmdline_leg0.bin oracle_cmdline_leg1.bin && \
   diff -q <(grep -E '^(STOP1|RAX=|RSI=|EFLAGS=|CR0=|CMDPTR=)' probe34_leg0.log) \
           <(grep -E '^(STOP1|RAX=|RSI=|EFLAGS=|CR0=|CMDPTR=)' probe34_leg1.log) >/dev/null; then
    echo "PHASE B PASS: x2 captures byte-identical (no variability fields observed)"
else
    echo "GATE FAIL: legs differ"
    exit 1
fi

# ---------- Phase C: non-vacuity ----------
# redA: flip one byte in the zeropage -> differ must flag
# The guard is the one line here beyond the rename, and it is why the rename is safe:
# the quoted heredoc needs the target as argv (shell expansion is off inside it), and
# unlike the sanity and redB heredocs above and below, this one had no '||' at HEAD --
# so a failed build fell straight through to a cmp of a 0-byte (or stale) file against
# leg0, which differs, which prints redA PASS. Per-run temps made that path quieter,
# not louder; this makes it a RED. Revert this guard alone if it is out of scope.
python3 - "$ZP_FLIP" <<'EOF' || { echo "GATE FAIL: redA mutant build errored"; exit 1; }
import sys
zp = bytearray(open('oracle_zp_leg0.bin','rb').read())
zp[0x228] ^= 0x01  # cmd_line_ptr LSB
open(sys.argv[1],'wb').write(bytes(zp))
EOF
if cmp -s oracle_zp_leg0.bin "$ZP_FLIP"; then
    echo "GATE FAIL: redA flip produced identical file (impossible)"; exit 1
else
    echo "PHASE C redA PASS: differ flags single flipped byte at zp[0x228] (cmd_line_ptr LSB)"
fi

# redB: a DIFFERENT kernel image (QEMU-direct boot of the same bzImage via
# its own loader, type_of_loader=0xff path) must produce a DIFFERENT
# zeropage in chainloader-owned fields. We reuse probe27's qemu-direct
# capture but only require difference in type_of_loader/0x210 region and
# cmdline content.
python3 probe27_qemu_direct.py >/dev/null 2>&1 || { echo "GATE FAIL: redB capture errored"; exit 1; }
python3 - <<'EOF' || { echo "GATE FAIL: redB differ did not flag"; exit 1; }
real = open('oracle_zp_leg0.bin','rb').read()
direct = open('qemu_leg0_zp.bin','rb').read()
assert len(real) == len(direct) == 4096
diffs = sum(1 for a, b in zip(real, direct) if a != b)
assert diffs > 16, f'only {diffs} bytes differ — schema not kernel-specific?'
print(f'PHASE C redB PASS: qemu-direct vs real-chain differ in {diffs} bytes')
EOF

# ---------- Phase D: pins ----------
echo "--- artifact sha256 pins ---"
sha256sum oracle_zp_leg0.bin oracle_zp_leg1.bin oracle_cmdline_leg0.bin \
          oracle_cmdline_leg1.bin probe34_leg0.log probe34_leg1.log \
          | tee oracle_pins.txt

echo "GATE PASS: BM901 oracle (x2 identical captures, differ REDs verified)"
exit 0
