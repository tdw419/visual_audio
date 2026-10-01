#!/usr/bin/env bash
# run_bm903_e2e.sh — TASK_BM903 ROW GATE (brief step 3).
#
# Closes the row: our own executed stage2 boots a PXC1 pixel medium carrying
# vmlinuz64 + core.gz, CRC32 gate v2 sits on the only path to the handoff, the
# handoff is BM902's, and the KERNEL ITSELF reaches the TinyCore shell marker on
# serial. Legs are the brief's L1..L6, in that order, each named in the output.
#
# Standing hard rule from BM901 (ROADMAP Rung 9): a mismatch surfaces as a DIFF,
# never as a hang. Every boot leg here runs under a stated wall-clock budget and
# a budget miss is a RED that names the budget. The two RED legs (L5, L6) must
# fail in the SAME clean run that goes green — if a leg cannot be made to fail,
# the gate is decoration and the row is not done.
#
# Serialization (MEASURED, see RECEIPT_BM903_STEP2.md): QEMU write-locks the
# image even for a read-only boot, and concurrent TCG guests were enough to turn
# an 11 s boot into a >240 s apparent stall. So legs run one at a time and S0b
# refuses to start beside any other bm903 qemu.
set -uo pipefail
cd "$(dirname "$0")"
# the probes are gate hands, and the brief scopes this row to rung9/, so they
# live beside the gate: a missing one is a broken rig, and S0 says so.

ATTEMPT_TIMEOUT=45 # one L3/L4 boot: the anchor lands at 11.0-12.0 s when the
                   # guest's autologin race resolves onto the serial console
BOOT_ATTEMPTS=8    # p(anchor per boot)~0.4-0.6, so the leg is allowed
                   # this many boots; 8 x 45 s is the same worst-case wall
                   # budget the single 180 s boot had, and it is all nominal:
                   # a systematic failure pays it in full and still goes RED.
L6_BUDGET=40       # the refusal must print inside this; measured 1.0 s
L6_GDB_WAIT=20     # how long we wait for a handoff stop that must NEVER come
GDB_TIMEOUT=120
STEP_TIMEOUT=60
BOOT_TIMEOUT=300

ANCHOR='tc@box'    # pinned in step 2, never re-chosen silently
pass=0; fail=0
ok()   { echo "  [PASS] $1"; pass=$((pass+1)); }
bad()  { echo "  [RED ] $1"; fail=$((fail+1)); }
hr()   { echo "----------------------------------------------------------------"; }

# These seven paths are this run's, not the machine's. Each is written by a leg here
# and read back by name by a later one, and three readers never check their writer:
# the L5 differ calls read bins whose heredocs are rc-untested, L4's cmp compares
# whatever .norm survived, and L6's host side is `cut` of a .crc the corruptor may
# not have refreshed. Measured on the leftovers of an earlier run, that last one
# costs the whole leg: with no boot and no corruption this run, the guest's serial
# line and the host's "independent prediction" both come off ten-hour-old files and
# agree, so all four of L6's verdicts print GREEN.
# bm903_norm_transcript.py:70 derives .norm from its argument and
# bm903_px_corrupt.py:68 writes DST.with_suffix('.crc'), and the .att$N siblings come
# off "${logf}" in boot_attempts — so one per-run DIRECTORY moves every derived form
# with its base, and one trap sweeps them. Note the two helpers do NOT agree: .norm is
# appended (p.suffix + '.norm') and .crc REPLACES the suffix, so the corrupt medium is
# $PX_CORRUPT and its prediction file is $PX_CRC, not "$PX_CORRUPT.crc" — measured,
# not read off the naming. The template must also keep the substring bm903:
# bm903_lane.py:35 finds a live boot by looking for it in qemu's argv, so a path
# without it would blind the serialization guard this file's header calls MEASURED.
E2E=$(mktemp -d "${TMPDIR:-/tmp}/bm903_e2e.XXXXXX") || { bad "mktemp -d E2E"; exit 1; }
trap 'rm -rf "$E2E"' EXIT
LEG0_LOG="$E2E/bm903_e2e_leg0.log"
LEG1_LOG="$E2E/bm903_e2e_leg1.log"
CTRL_LOG="$E2E/bm903_e2e_ctrl.log"
L6_LOG="$E2E/bm903_e2e_l6.log"
ZP_MUTANT="$E2E/bm903_px_zp_mutant.bin"
ZP_WHITE="$E2E/bm903_px_zp_white.bin"
PX_CORRUPT="$E2E/bm903_medium_px_corrupt.raw"
PX_CRC="$E2E/bm903_medium_px_corrupt.crc"

# ============================================================ S0 input pins
hr; echo "S0  input pins (nothing downstream is trusted past this line)"
declare -A PIN=(
  [vmlinuz64.extracted]=ee4545bb3eff57fabc1788aa5f776081dad200ea8019e1ef8a09a931a74db680
  [../rung7/core.gz]=7f1e370dd4e489fd76c99f76ed9ddd79fd7e51f23af457b07071b3898bb8b5a2
  [oracle_zp_leg0.bin]=c3120d8ef78f6a66a8fe09e5f1f6ba967f216e07a2fabbd9430a32daca051f16
  [oracle_cmdline_leg0.bin]=30cd829f2a88c80cb80bfef1d056c9d0d85683cc9e58dbd7b9e4c62ce03c43c3
  [bm902_zp.bin]=f6605707f28f97130fc6313e567993b0b012ea4bf7166be7fea4d46de9deadac
  [bm902_cmdline.bin]=30cd829f2a88c80cb80bfef1d056c9d0d85683cc9e58dbd7b9e4c62ce03c43c3
)
s0=1
for f in "${!PIN[@]}"; do
  got=$(sha256sum "$f" | cut -d' ' -f1)
  if [[ "$got" == "${PIN[$f]}" ]]; then ok "pin $f"
  else bad "pin $f: got ${got:0:16}… want ${PIN[$f]:0:16}…"; s0=0; fi
done
# the gate constant the guest bakes must be the one the codec measured
gate_crc=$(sed -n 's/^%define EXPECTED_CRC 0x\([0-9A-F]*\)$/\1/p' bm903_px_layout.inc)
meta_crc=$(python3 -c "import json;print(json.load(open('bm903_px_meta.json'))['payload_crc32'])")
[[ "$gate_crc" == "$meta_crc" ]] && ok "EXPECTED_CRC $gate_crc == codec meta (one source of truth)" \
  || bad "gate baked $gate_crc but the codec measured $meta_crc"
# rig check: the probes are legs' only hands — a missing one is a broken gate,
# not a failed leg, so name it here before any boot can mask it as rc=2.
for p in bm903_anchor_boot.py bm903_norm_transcript.py bm903_px_corrupt.py; do
  [[ -f $p ]] && ok "probe $p" || bad "probe MISSING: $p"
done
[[ $s0 -eq 1 ]] || { echo "S0 RED — aborting before any build"; exit 1; }

# ========================================================= S0b lane contract
hr; echo "S0b lane guard: no other bm903 boot may be alive"
if timeout $STEP_TIMEOUT python3 bm903_lane.py bm903_medium_px.raw; then ok "lane clear"; else
  bad "lane busy — legs cannot be timed or locked while another boot runs"; exit 1; fi

# =============================================================== S1 build
hr; echo "S1  build both media (step-1 contiguous and step-2 pixel) from source"
timeout $STEP_TIMEOUT python3 bm903_consts.py   > bm903_e2e_consts.log 2>&1 \
  && ok "bm903_consts.py" || { bad "bm903_consts.py"; tail -5 bm903_e2e_consts.log; exit 1; }
timeout $STEP_TIMEOUT python3 bm903_mkimg.py    > bm903_e2e_mkimg.log 2>&1 \
  && ok "bm903_mkimg.py (step-1 medium)" || { bad "bm903_mkimg.py"; tail -5 bm903_e2e_mkimg.log; exit 1; }
timeout $STEP_TIMEOUT python3 bm903_mkimg_px.py > bm903_e2e_mkimg_px.log 2>&1 \
  && ok "bm903_mkimg_px.py (pixel medium)" || { bad "bm903_mkimg_px.py"; cat bm903_e2e_mkimg_px.log; exit 1; }
cat bm903_e2e_mkimg_px.log | sed 's/^/      /'
grep -qi 'warning' bm903_e2e_mkimg_px.log && bad "nasm warned" || ok "nasm clean (no warnings)"
for m in bm903_medium.raw bm903_medium_px.raw; do
  [[ -f $m ]] && ok "$m present ($(stat -c%s $m) B)" || bad "$m missing"
done
PXSECT=$(( $(stat -c%s bm903_medium_px.raw) / 512 ))
want_sect=$(python3 -c "
import re
d={m.group(1):int(m.group(2),0) for m in re.finditer(r'^%define (\w+) (-?0x[0-9A-Fa-f]+|\d+)\$',open('bm903_px_layout.inc').read(),re.M)}
print(d['PX_BASE_LBA']+4*d['PX_PLANE_SECTORS'])")
[[ "$PXSECT" -eq "$want_sect" ]] && ok "pixel medium $PXSECT sectors == layout (every plane chunk is inside the file)" \
  || bad "pixel medium $PXSECT != layout $want_sect"

# ============================================ L1 executed-vs-constructed (1/2)
hr; echo "L1  boot the PIXEL medium, stop on the kernel's first insn, diff vs BM902"
timeout $BOOT_TIMEOUT python3 bm903_capture.py bm903_medium_px.raw bm903_px \
        > bm903_e2e_capture.log 2>&1
rc=$?
grep -E 'leg [01]:' bm903_e2e_capture.log | sed 's/^/      /'
[[ $rc -eq 0 ]] && ok "capture rc=0 (both legs stopped at 0x100000 with HdrS at \$rsi)" \
  || bad "capture rc=$rc — timeout or no stop (hang = failure, budget ${BOOT_TIMEOUT}s)"
for leg in 0 1; do
  grep -q 'BM903-S2 GATE2=PASS' bm903_px_serial_leg$leg.log \
    && ok "leg $leg executed the walk AND passed gate v2 (serial, not host-side)" \
    || bad "leg $leg serial lacks GATE2=PASS — did the executed path run at all?"
done
for leg in 0 1; do
  timeout $STEP_TIMEOUT python3 bm903_differ.py \
      bm903_px_zp_leg$leg.bin bm903_px_cmdline_leg$leg.bin bm903_px_regs_leg$leg.json \
      > bm903_e2e_differ_leg$leg.log 2>&1
  rc=$?
  sed 's/^/      /' bm903_e2e_differ_leg$leg.log
  [[ $rc -eq 0 ]] && ok "leg $leg L1 green (whitelist-only diffs)" || bad "leg $leg differ rc=$rc"
done

# ------------------------------------------- L1b cross-medium identity (extra)
hr; echo "L1b the pixel medium and the contiguous medium construct the SAME handoff"
timeout $BOOT_TIMEOUT python3 bm903_capture.py bm903_medium.raw bm903 > bm903_e2e_capture1.log 2>&1 \
  && ok "step-1 medium re-captured" || bad "step-1 capture rc=$?"
for f in zp cmdline; do
  cmp -s bm903_px_${f}_leg0.bin bm903_${f}_leg0.bin \
    && ok "bm903_px_${f}_leg0.bin == bm903_${f}_leg0.bin (byte-identical)" \
    || bad "${f}: the two media do not construct the same handoff"
done

# ============================================================ L2 registers
hr; echo "L2  GPRs / segments / CR0 / EFLAGS / rsp at 0x100000 vs the oracle"
l2=$(python3 - <<'REGPY'
import json
want = {'rsp': 0x1f784, 'cr0': 0x11, 'eflags': 0x46, 'cs': 0x10, 'ss': 0x18,
        'ds': 0x18, 'es': 0x18, 'rsi': 0x13ab0, 'rip': 0x100000, 'rax': 0x100000}
bad = []
for leg in (0, 1):
    r = json.load(open(f'bm903_px_regs_leg{leg}.json'))
    bad += [f'leg{leg}.{k}={r.get(k):#x} want {v:#x}'
            for k, v in want.items() if r.get(k) != v]
    zero = ('rbx', 'rcx', 'rdx', 'rdi', 'rbp', 'r8', 'r9', 'r10', 'r11',
            'r12', 'r13', 'r14', 'r15', 'cr3', 'cr4')
    bad += [f'leg{leg}.{k}={r.get(k):#x} want 0' for k in zero if r.get(k) != 0]
print('pinned rsp=0x1f784 cr0=0x11 eflags=0x46 cs=0x10 ss/ds/es=0x18 '
      'rsi=0x13ab0 rip=rax=0x100000; 15 more = 0 -> '
      + ('ALL 26 MATCH' if not bad else 'DIVERGE: ' + '; '.join(bad)))
raise SystemExit(0 if not bad else 1)
REGPY
)
rc=$?
echo "      $l2"
[[ $rc -eq 0 ]] && ok "L2 green on both pixel legs (the differ's L3 line checked all 25 vs the oracle; this re-pins the load-bearing ones)" \
  || bad "L2 registers diverge from the oracle"

# ========================================================= L3 serial anchor
# boot_attempts <medium> <log> — up to $BOOT_ATTEMPTS boots, each under
# $ATTEMPT_TIMEOUT s, until the serial transcript carries $ANCHOR. Prints the
# boot index and rc of the winning attempt on stdout; every losing attempt is
# named on stderr, so nothing disappears into the gate's own logs.
#
# WHY A LEG THIS DETERMINISTIC-WANTED BOOTS MORE THAN ONCE (measured,
# rung9/bm903_tty_race.py): Tiny Core's inittab respawns
#   tty1 ::respawn:/sbin/getty -nl /sbin/autologin 38400 tty1
#   ttyS0::respawn:/sbin/getty -nl /sbin/autologin 115200 ttyS0
# and /sbin/autologin is
#   if [ -f /var/log/autologin ]; then exec /sbin/getty 38400 tty1
#   else touch /var/log/autologin; exec login -f root; fi
# The FIRST getty to touch that flag file owns `login -f root`; the loser is
# re-execed onto tty1 unconditionally and so never draws a prompt on serial.
# Which one wins is guest-internal scheduling, and it is a coin, not a skewing
# one: 19 timed pixel boots anchored 11 times, 8 step-1 boots anchored 3 times
# (step-1's guest RAM at the handoff is byte-identical to the pixel one, L1b),
# and extending a single boot's budget does NOT rescue a loss — two 90 s pixel
# boots sat silent after `login[494]: root login on 'tty1'`. `-vga none`, to
# remove the tty1 rival entirely, anchored 6/8: indistinguishable. So which
# console autologin lands on is not a property of our loader, and the leg says
# so instead of pretending the coin flip is ours. The anchor string itself is
# untouched; the data is reproducible with rung9/bm903_tty_race.py.
boot_attempts() {
  local med=$1 logf=$2 a rc
  for a in $(seq 1 $BOOT_ATTEMPTS); do
    timeout $((ATTEMPT_TIMEOUT+25)) python3 bm903_anchor_boot.py \
        "$med" "$logf" $ATTEMPT_TIMEOUT > "${logf}.att$a" 2>&1
    rc=$?
    if [[ $rc -eq 0 ]] && grep -qa "$ANCHOR" "$logf"; then
      echo "$a $rc"; return 0
    fi
    echo "      boot $a/$BOOT_ATTEMPTS rc=$rc: no $ANCHOR on serial (${ATTEMPT_TIMEOUT}s budget; guest autologin race)" >&2
  done
  return 1
}

hr; echo "L3  the kernel speaks on serial and reaches '$ANCHOR'"
echo "    (up to $BOOT_ATTEMPTS boots x ${ATTEMPT_TIMEOUT}s — which tty autologin wins is Tiny Core's, not ours)"
got=$(boot_attempts bm903_medium_px.raw "$LEG0_LOG"); rc=$?
if [[ $rc -eq 0 ]]; then
  read -r att arc <<< "$got"
  sed 's/^/      /' "$LEG0_LOG.att$att"
  ok "L3 green: pixel medium -> kernel -> $ANCHOR on boot $att of $BOOT_ATTEMPTS (${ATTEMPT_TIMEOUT}s each, rc=$arc)"
else
  sed 's/^/      /' "$LEG0_LOG.att$BOOT_ATTEMPTS" 2>/dev/null
  bad "L3 RED: $BOOT_ATTEMPTS pixel boots, none reached '$ANCHOR' inside ${ATTEMPT_TIMEOUT}s — not the rig's fault, the leg failed"
fi
# the step-1 medium as a live control in the same run
# control: the step-1 medium under the same policy. Its job is attribution —
# the measured race hits it too, so a control RED is the rig or the race, never
# the pixel path; the old wording claimed the opposite and the data disproved it.
got=$(boot_attempts bm903_medium.raw "$CTRL_LOG"); rc=$?
if [[ $rc -eq 0 ]]; then
  read -r catt carc <<< "$got"
  grep -E 'elapsed' "$CTRL_LOG.att$catt" | sed 's/^/      control /'
  ok "control: the contiguous medium reaches $ANCHOR (boot $catt, rc=$carc) — the rig boots"
else
  bad "control: $BOOT_ATTEMPTS step-1 boots reached no $ANCHOR either — rig or race; the pixel verdict is void"
fi

# ================================================== L4 x2 determinism
hr; echo "L4  two boots of the pixel medium: transcripts and dumps"
got=$(boot_attempts bm903_medium_px.raw "$LEG1_LOG"); rc=$?
if [[ $rc -eq 0 ]]; then
  read -r att2 arc2 <<< "$got"
  ok "second pixel boot reached $ANCHOR (boot $att2 of $BOOT_ATTEMPTS, rc=$arc2)"
else
  bad "L4 RED: $BOOT_ATTEMPTS further pixel boots, none reached $ANCHOR (${ATTEMPT_TIMEOUT}s each)"
fi
python3 bm903_norm_transcript.py "$LEG0_LOG" "$LEG1_LOG" \
  | sed 's/^/      /'
cmp "$LEG0_LOG.norm" "$LEG1_LOG.norm" \
  && ok "transcripts byte-identical after T1-T4 (compared up to the getty race)" \
  || { bad "transcripts diverge — show the diff:"; diff "$LEG0_LOG.norm" "$LEG1_LOG.norm" | head -12 | sed 's/^/      /'; }
for pair in bm903_px_zp_leg0.bin:bm903_px_zp_leg1.bin \
            bm903_px_cmdline_leg0.bin:bm903_px_cmdline_leg1.bin \
            bm903_px_regs_leg0.json:bm903_px_regs_leg1.json; do
  a=${pair%%:*}; b=${pair##*:}
  cmp -s "$a" "$b" && ok "handoff dumps: $a == $b (strict, no normalization)" \
    || bad "$a != $b (non-deterministic capture)"
done

# ================================================= L5 RED single byte
hr; echo "L5  RED — flip ONE zeropage byte outside the whitelist; the differ must name it"
python3 - "$ZP_MUTANT" <<'PY'
import sys
from pathlib import Path
b = bytearray(Path('bm903_px_zp_leg0.bin').read_bytes())
OFF = 0x244                     # version_string: MUST-MATCH, kernel-baked, not whitelisted
assert b[OFF] == 0, f'fixture byte at {OFF:#x} is not 0 — pick another offset'
b[OFF] ^= 0x01
Path(sys.argv[1]).write_bytes(bytes(b))
print('  mutant: 0x244 0x00 -> 0x01 (outside every whitelist row)')
PY
timeout $STEP_TIMEOUT python3 bm903_differ.py "$ZP_MUTANT" \
    bm903_px_cmdline_leg0.bin bm903_px_regs_leg0.json --expect-fail \
    > bm903_e2e_l5.log 2>&1
rc=$?; sed 's/^/      /' bm903_e2e_l5.log
[[ $rc -eq 0 ]] && ok "L5 green: mutant caught, differ exits non-zero naming 0x244" \
  || bad "L5 RED: mutant NOT caught — the differ is decoration"
# and its control: a whitelisted byte must NOT be flagged (specificity, not noise)
python3 - "$ZP_WHITE" <<'PY'
import sys
from pathlib import Path
b = bytearray(Path('bm903_px_zp_leg0.bin').read_bytes())
b[0x210] ^= 0x01                # type_of_loader: a whitelisted row
Path(sys.argv[1]).write_bytes(bytes(b))
PY
timeout $STEP_TIMEOUT python3 bm903_differ.py "$ZP_WHITE" \
    bm903_px_cmdline_leg0.bin bm903_px_regs_leg0.json > bm903_e2e_l5c.log 2>&1
rc=$?; grep -E '^L1' bm903_e2e_l5c.log | sed 's/^/      control /'
[[ $rc -eq 0 ]] && ok "L5 control: a whitelisted change stays green" \
  || bad "L5 control RED: whitelisted byte flagged — the whitelist is not honoured"

# ============================================= L6 RED medium corruption
hr; echo "L6  RED — corrupt ONE medium byte: gate refuses, host arithmetic cross-checks, NO jump"
python3 bm903_px_corrupt.py "$PWD/bm903_medium_px.raw" \
        "$PX_CORRUPT" 4000000 | sed 's/^/      /'
pred=$(cut -d' ' -f1 "$PX_CRC")
expct=$(cut -d' ' -f2 "$PX_CRC")
timeout $((L6_BUDGET+30)) python3 bm903_anchor_boot.py \
    "$PX_CORRUPT" "$L6_LOG" $L6_BUDGET \
    > bm903_e2e_l6boot.log 2>&1
rc=$?; sed -n 's/^/      /p' bm903_e2e_l6boot.log | head -12
line=$(grep -ao 'BM903-S2 GATE2 CRC=[0-9A-F]* EXP=[0-9A-F]*' "$L6_LOG" | head -1)
echo "      guest printed: ${line:-<nothing>}"
echo "      host predicted: BM903-S2 GATE2 CRC=$pred EXP=$expct"
[[ "$line" == "BM903-S2 GATE2 CRC=$pred EXP=$expct" ]] \
  && ok "L6 cross-check: the guest's computed CRC == the host's independent prediction, and != EXPECTED" \
  || bad "L6 RED: guest CRC line does not match the host prediction — arithmetic or fixture is wrong"
grep -qa 'GATE2=FAIL' "$L6_LOG" \
  && ok "L6 refusal present (rung-4 format: computed then expected, then the verdict)" \
  || bad "L6 RED: no refusal on serial"
grep -qa 'HANDOFF BUILT' "$L6_LOG" \
  && bad "L6 RED: the handoff was built DESPITE the mismatch — the gate is not on the only path" \
  || ok "no 'HANDOFF BUILT' after the refusal"
grep -qa "$ANCHOR" "$L6_LOG" \
  && bad "L6 RED: the corrupted medium reached $ANCHOR anyway" || ok "no anchor from the corrupted medium"
# and the debugger's view: the kernel's first instruction is NEVER reached
timeout 120 python3 bm903_capture.py "$PX_CORRUPT" bm903_l6red $L6_GDB_WAIT \
    > bm903_e2e_l6cap.log 2>&1
rc=$?; grep -E 'leg [01]:' bm903_e2e_l6cap.log | sed 's/^/      /'
if [[ $rc -ne 0 ]] && ! grep -q 'stop=stopped on the handoff' bm903_e2e_l6cap.log; then
  ok "L6 no-jump proven under gdb: no stop at 0x100000 within ${L6_GDB_WAIT}s x2 legs (rc=$rc)"
else
  bad "L6 RED: the corrupted medium DID stop on the kernel entry — the refusal did not stop the jump"
fi

# ================================================= regression, same run
hr; echo "R1  the step-1 gate still passes with these files in place"
timeout $BOOT_TIMEOUT bash run_bm903_step1.sh > bm903_e2e_step1.log 2>&1
rc=$?; tail -4 bm903_e2e_step1.log | sed 's/^/      /'
[[ $rc -eq 0 ]] && ok "step-1 gate green" || bad "step-1 gate rc=$rc — regression"

# ================================================================= tally
hr
echo "BM903 E2E TALLY: $pass pass, $fail red"
if [[ $fail -eq 0 ]]; then
  echo "BM903 ROW GREEN: the PXC1 pixel medium carries bzImage+initrd, executed"
  echo "stage2 builds the BM902 handoff (4 whitelisted bytes), CRC32 gate v2 is"
  echo "the only path to it (and refuses on a single corrupted byte, with the"
  echo "guest's own arithmetic matching the host's), and the kernel reaches"
  echo "'$ANCHOR' on serial (guest-autologin-race allowance: $BOOT_ATTEMPTS boots x"
  echo "${ATTEMPT_TIMEOUT}s, each named). Both RED legs fired."
  exit 0
fi
echo "BM903 ROW RED — see the legs above"
exit 1
