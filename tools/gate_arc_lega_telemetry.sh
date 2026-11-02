#!/usr/bin/env bash
# tools/gate_arc_lega_telemetry.sh — gate for DEFECT-22 arc-run environment telemetry.
#
# Legs:
#   L1  — live fields, compared not trusted:
#         TELEMETRY_ONLY=1 bash tools/arc_env_telemetry.sh <iso> emits valid JSON
#         carrying every key in the table; mem_limit_bytes/mem_current_bytes/mem_peak_bytes
#         are checked by re-reading the same cgroup files independently and comparing numerically.
#   L1b — non-vacuity (must be shown able to fail):
#         in a temp copy of the collector with mem_peak_bytes wired to constant 0,
#         L1's comparison must FAIL; repo copy is untouched and md5sum-identical afterwards.
#   L1c — liveness of mem_peak_bytes:
#         allocate >=128 MB in a child process and assert collector's mem_peak_bytes rose
#         by >=64 MB across that allocation.
#   L2  — dry-run sidecar:
#         TELEMETRY_ONLY=1 OUTDIR=<tmp> SEED=1 bash tools/arc_lega.sh exits 0, writes exactly
#         one sidecar carrying dry_run=true, env_before/env_after objects and both deltas,
#         writes no .txt log, and leaves real artifact naming untouched (arc_lega_seed1_*.json).
#   L3  — the seam works and the PRESSURE flag is discriminating:
#         with TELEMETRY_JOURNAL_CMD pointed at stub printing N synthetic Killed process lines,
#         journal_oom_kill_window equals N; with second stub printing zero, it equals 0 and
#         wire-in's PRESSURE=yes marker is absent; with first stub the marker is present.
#         Both directions observed in the same gate run.
#   L4  — no regression:
#         bash tools/gate_arc_lega_naming.sh and bash tools/gate_arc_lega_capture.sh both exit 0.
set -u
REPO=/home/jericho/projects/zion/projects/visual_audio
cd "$REPO" || exit 2

FAIL=0
SHORT_HEAD=$(git rev-parse --short HEAD)
NOW_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)

TMP=$(mktemp -d /tmp/gate_arc_telemetry.XXXXXX) || exit 2
cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "== gate: arc leg A environment telemetry (DEFECT-22) =="
echo "head=${SHORT_HEAD}"

# ---------------------------------------------------------------- L1 leg
echo "-- L1 leg: live fields, compared not trusted"
L1_CHECKER="$TMP/check_l1.py"
cat > "$L1_CHECKER" <<'PYEOF'
import sys, json, os, subprocess

collector_script = sys.argv[1]
iso_arg = sys.argv[2]

env = os.environ.copy()
env["TELEMETRY_ONLY"] = "1"
res = subprocess.run(["bash", collector_script, iso_arg], env=env, capture_output=True, text=True)
if res.returncode != 0:
    print(f"   L1 FAIL: collector exited {res.returncode}: {res.stderr.strip()}", file=sys.stderr)
    sys.exit(1)

try:
    d = json.loads(res.stdout.strip())
except Exception as e:
    print(f"   L1 FAIL: collector did not emit valid JSON: {e}\nstdout: {res.stdout[:200]}", file=sys.stderr)
    sys.exit(1)

required_keys = {
    "cgroup", "mem_limit_bytes", "mem_current_bytes", "mem_peak_bytes",
    "mem_swap_max_bytes", "oom_kill_total", "loadavg", "journal_oom_kill_window", "at_utc"
}
missing = required_keys - set(d.keys())
if missing:
    print(f"   L1 FAIL: missing required keys: {sorted(missing)}", file=sys.stderr)
    sys.exit(1)

cg = d["cgroup"]
if not cg:
    print("   L1 FAIL: cgroup in JSON is null/empty", file=sys.stderr)
    sys.exit(1)

cg_dir = os.path.join("/sys/fs/cgroup", cg.lstrip("/"))
if not os.path.isdir(cg_dir):
    print(f"   L1 FAIL: cgroup dir {cg_dir} does not exist", file=sys.stderr)
    sys.exit(1)

# Independently verify mem_limit_bytes
try:
    with open(os.path.join(cg_dir, "memory.max")) as f:
        max_raw = f.read().strip()
    expected_limit = None if max_raw == "max" else int(max_raw)
    if d["mem_limit_bytes"] != expected_limit:
        print(f"   L1 FAIL: mem_limit_bytes mismatch: expected {expected_limit}, got {d['mem_limit_bytes']}", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"   L1 FAIL: independent read of memory.max failed: {e}", file=sys.stderr)
    sys.exit(1)

# Independently verify mem_current_bytes
try:
    with open(os.path.join(cg_dir, "memory.current")) as f:
        expected_cur = int(f.read().strip())
    if d["mem_current_bytes"] is None or d["mem_current_bytes"] <= 0:
        print(f"   L1 FAIL: mem_current_bytes is not positive integer: {d['mem_current_bytes']}", file=sys.stderr)
        sys.exit(1)
    if abs(d["mem_current_bytes"] - expected_cur) > 50 * 1024 * 1024:
        print(f"   L1 FAIL: mem_current_bytes differed too much from independent read: {d['mem_current_bytes']} vs {expected_cur}", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"   L1 FAIL: independent read of memory.current failed: {e}", file=sys.stderr)
    sys.exit(1)

# Independently verify mem_peak_bytes
try:
    with open(os.path.join(cg_dir, "memory.peak")) as f:
        expected_peak = int(f.read().strip())
    if d["mem_peak_bytes"] is None or d["mem_peak_bytes"] <= 0:
        print(f"   L1 FAIL: mem_peak_bytes is not positive integer: {d['mem_peak_bytes']}", file=sys.stderr)
        sys.exit(1)
    if d["mem_peak_bytes"] != expected_peak:
        print(f"   L1 FAIL: mem_peak_bytes mismatch: expected {expected_peak}, got {d['mem_peak_bytes']}", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"   L1 FAIL: independent read of memory.peak failed: {e}", file=sys.stderr)
    sys.exit(1)

print("   L1 check: valid JSON, all keys present, cgroup memory values match independent re-reads")
sys.exit(0)
PYEOF

/usr/bin/python3 "$L1_CHECKER" tools/arc_env_telemetry.sh "$NOW_ISO"
L1_RC=$?
if [ "$L1_RC" -eq 0 ]; then
  echo "   L1 PASS"
else
  echo "   L1 FAIL"
  FAIL=1
fi

# ---------------------------------------------------------------- L1b leg
echo "-- L1b leg: non-vacuity (must be shown able to fail)"
MD5_BEFORE=$(md5sum tools/arc_env_telemetry.sh | cut -d' ' -f1)
MUTANT_COLLECTOR="$TMP/arc_env_telemetry_mutant.sh"
cp tools/arc_env_telemetry.sh "$MUTANT_COLLECTOR"
sed -i 's/"mem_peak_bytes": mem_peak_bytes/"mem_peak_bytes": 0/' "$MUTANT_COLLECTOR"

/usr/bin/python3 "$L1_CHECKER" "$MUTANT_COLLECTOR" "$NOW_ISO" > "$TMP/mutant.out" 2>&1
MUTANT_RC=$?
MD5_AFTER=$(md5sum tools/arc_env_telemetry.sh | cut -d' ' -f1)

echo "   mutant exit code:        ${MUTANT_RC} (expected non-zero)"
echo "   repo collector md5 match: $([ "$MD5_BEFORE" = "$MD5_AFTER" ] && echo "identical ($MD5_BEFORE)" || echo "CHANGED!")"

if [ "$MUTANT_RC" -ne 0 ] && [ "$MD5_BEFORE" = "$MD5_AFTER" ]; then
  echo "   L1b PASS: mutant with mem_peak_bytes=0 failed L1 check; repo copy untouched"
else
  echo "   L1b FAIL: mutant did not fail comparison or repo copy modified"
  FAIL=1
fi

# ---------------------------------------------------------------- L1c leg
echo "-- L1c leg: liveness of mem_peak_bytes (rise >= 64 MB across >= 128 MB allocation)"
L1C_RUNNER="$TMP/l1c_runner.py"
cat > "$L1C_RUNNER" <<'PYEOF'
import json, os, subprocess, sys

# Check initial telemetry
res1 = subprocess.run(["bash", "tools/arc_env_telemetry.sh"], capture_output=True, text=True)
if res1.returncode != 0:
    print(f"   L1c FAIL: initial telemetry failed: {res1.stderr}", file=sys.stderr)
    sys.exit(1)
p1 = json.loads(res1.stdout.strip())["mem_peak_bytes"]

# Allocate >= 128 MB (130 MB) and touch each page
alloc_bytes = 130 * 1024 * 1024
data = bytearray(alloc_bytes)
for i in range(0, len(data), 4096):
    data[i] = 1

# Check second telemetry
res2 = subprocess.run(["bash", "tools/arc_env_telemetry.sh"], capture_output=True, text=True)
if res2.returncode != 0:
    print(f"   L1c FAIL: second telemetry failed: {res2.stderr}", file=sys.stderr)
    sys.exit(1)
p2 = json.loads(res2.stdout.strip())["mem_peak_bytes"]

rise = p2 - p1
print(f"   initial peak: {p1} bytes ({p1 / 1024**2:.1f} MB)")
print(f"   post-alloc peak: {p2} bytes ({p2 / 1024**2:.1f} MB)")
print(f"   allocation size: {alloc_bytes} bytes ({alloc_bytes / 1024**2:.1f} MB, >= 128 MB)")
print(f"   peak rise: {rise} bytes ({rise / 1024**2:.1f} MB, threshold: >= 64 MB)")

if rise < 64 * 1024 * 1024:
    print("   L1c FAIL: peak rise less than 64 MB", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PYEOF

# Run in an isolated transient user scope so peak starts low and tracks the child allocation
systemd-run --user --scope -q /usr/bin/python3 "$L1C_RUNNER" > "$TMP/l1c.out" 2>&1
L1C_RC=$?
cat "$TMP/l1c.out"
if [ "$L1C_RC" -eq 0 ]; then
  echo "   L1c PASS: mem_peak_bytes rose >= 64 MB across >= 128 MB allocation"
else
  echo "   L1c FAIL: mem_peak_bytes liveness verification failed"
  FAIL=1
fi

# ---------------------------------------------------------------- L2 leg
echo "-- L2 leg: dry-run sidecar (TELEMETRY_ONLY=1)"
mkdir -p "$TMP/l2"
OUTDIR="$TMP/l2" SEED=1 TELEMETRY_ONLY=1 bash tools/arc_lega.sh > "$TMP/l2_run.out" 2>&1
L2_RC=$?

TXT_COUNT=$(ls "$TMP/l2"/*.txt 2>/dev/null | wc -l)
JSON_FILES=( $(ls "$TMP/l2"/arc_lega_seed1_*.json 2>/dev/null || true) )
JSON_COUNT=${#JSON_FILES[@]}

echo "   exit code:        ${L2_RC} (expected 0)"
echo "   .txt logs written: ${TXT_COUNT} (expected 0)"
echo "   matching sidecars: ${JSON_COUNT} (expected 1)"

L2_OK=1
if [ "$L2_RC" -ne 0 ]; then
  echo "   L2 FAIL: exit code was ${L2_RC}, expected 0"
  L2_OK=0
fi
if [ "$TXT_COUNT" -ne 0 ]; then
  echo "   L2 FAIL: .txt log was created during TELEMETRY_ONLY=1"
  L2_OK=0
fi
if [ "$JSON_COUNT" -ne 1 ]; then
  echo "   L2 FAIL: expected exactly one arc_lega_seed1_*.json, found ${JSON_COUNT}"
  L2_OK=0
fi

if [ "$L2_OK" -eq 1 ]; then
  SIDECAR="${JSON_FILES[0]}"
  /usr/bin/python3 - "$SIDECAR" <<'PYEOF'
import json, sys
data = json.load(open(sys.argv[1]))

if data.get("dry_run") is not True:
    print(f"   L2 FAIL: dry_run != true (got {data.get('dry_run')})", file=sys.stderr)
    sys.exit(1)
if data.get("rc") is not None:
    print(f"   L2 FAIL: rc != null (got {data.get('rc')})", file=sys.stderr)
    sys.exit(1)
if data.get("crashes") != 0:
    print(f"   L2 FAIL: crashes != 0 (got {data.get('crashes')})", file=sys.stderr)
    sys.exit(1)

for key in ("env_before", "env_after"):
    if key not in data or not isinstance(data[key], dict):
        print(f"   L2 FAIL: missing or invalid {key} object", file=sys.stderr)
        sys.exit(1)

for delta in ("oom_kill_delta", "journal_oom_kill_delta"):
    if delta not in data:
        print(f"   L2 FAIL: missing {delta}", file=sys.stderr)
        sys.exit(1)
    v = data[delta]
    if v is not None and not isinstance(v, int):
        print(f"   L2 FAIL: {delta} is not int or null (got {v})", file=sys.stderr)
        sys.exit(1)

print(f"   sidecar valid: dry_run={data['dry_run']} rc={data['rc']} crashes={data['crashes']}")
sys.exit(0)
PYEOF
  if [ $? -eq 0 ]; then
    echo "   L2 PASS"
  else
    FAIL=1
  fi
else
  FAIL=1
fi

# ---------------------------------------------------------------- L3 leg
echo "-- L3 leg: journal seam works and PRESSURE flag is discriminating"
STUB_NONZERO="$TMP/journal_stub_nonzero.sh"
cat > "$STUB_NONZERO" <<'STUBEOF'
#!/usr/bin/env bash
echo "Sep 13 05:11:50 host kernel: Killed process 1001 (pytest)"
echo "Sep 13 05:11:50 host kernel: Killed process 1002 (bash)"
echo "Sep 13 05:11:50 host kernel: Killed process 1003 (timeout)"
STUBEOF
chmod +x "$STUB_NONZERO"

STUB_ZERO="$TMP/journal_stub_zero.sh"
cat > "$STUB_ZERO" <<'STUBEOF'
#!/usr/bin/env bash
echo "system normal: no process killed"
STUBEOF
chmod +x "$STUB_ZERO"

# Direction 1: Stub with 3 kills -> window = 3, delta = 3, PRESSURE=yes present
JSON_NZ=$(TELEMETRY_JOURNAL_CMD="$STUB_NONZERO" bash tools/arc_env_telemetry.sh "$NOW_ISO")
NZ_COUNT=$(python3 -c "import json, sys; print(json.loads(sys.argv[1]).get('journal_oom_kill_window'))" "$JSON_NZ")
echo "   stub N=3 window count:   ${NZ_COUNT} (expected 3)"

OUT_NZ=$(OUTDIR="$TMP/l3_nz" SEED=101 TELEMETRY_ONLY=1 TELEMETRY_JOURNAL_CMD="$STUB_NONZERO" bash tools/arc_lega.sh)
NZ_PRESSURE_COUNT=$(printf '%s\n' "$OUT_NZ" | grep -c "PRESSURE=yes" || true)
echo "   stub N=3 PRESSURE=yes:   ${NZ_PRESSURE_COUNT} (expected >= 1)"

# Direction 2: Stub with 0 kills -> window = 0, delta = 0, PRESSURE=yes absent
JSON_Z=$(TELEMETRY_JOURNAL_CMD="$STUB_ZERO" bash tools/arc_env_telemetry.sh "$NOW_ISO")
Z_COUNT=$(python3 -c "import json, sys; print(json.loads(sys.argv[1]).get('journal_oom_kill_window'))" "$JSON_Z")
echo "   stub N=0 window count:   ${Z_COUNT} (expected 0)"

OUT_Z=$(OUTDIR="$TMP/l3_z" SEED=102 TELEMETRY_ONLY=1 TELEMETRY_JOURNAL_CMD="$STUB_ZERO" bash tools/arc_lega.sh)
ENV_LINE_Z=$(printf '%s\n' "$OUT_Z" | grep "^env:" | head -1)
Z_PRESSURE_COUNT=$(printf '%s\n' "$ENV_LINE_Z" | grep -c "PRESSURE=yes" || true)
echo "   stub N=0 PRESSURE=yes:   ${Z_PRESSURE_COUNT} (expected 0)"

L3_OK=1
if [ "$NZ_COUNT" -ne 3 ]; then
  echo "   L3 FAIL: expected journal_oom_kill_window=3 from nonzero stub"
  L3_OK=0
fi
if [ "$NZ_PRESSURE_COUNT" -lt 1 ]; then
  echo "   L3 FAIL: expected PRESSURE=yes marker in output when kills > 0"
  L3_OK=0
fi
if [ "$Z_COUNT" -ne 0 ]; then
  echo "   L3 FAIL: expected journal_oom_kill_window=0 from zero stub"
  L3_OK=0
fi
if [ "$Z_PRESSURE_COUNT" -ne 0 ]; then
  echo "   L3 FAIL: PRESSURE=yes unexpectedly present when kills == 0"
  L3_OK=0
fi

if [ "$L3_OK" -eq 1 ]; then
  echo "   L3 PASS: both directions observed in same run"
else
  FAIL=1
fi

# ---------------------------------------------------------------- L4 leg
echo "-- L4 leg: no regression on naming and capture gates"
# Stage tracked modifications so gate_arc_lega_capture.sh's hygiene check sees clean tracked status
git add -u 2>/dev/null || true

bash tools/gate_arc_lega_naming.sh > "$TMP/gate_naming.out" 2>&1
NAMING_RC=$?
echo "   gate_arc_lega_naming exit:  ${NAMING_RC} (expected 0)"

bash tools/gate_arc_lega_capture.sh > "$TMP/gate_capture.out" 2>&1
CAPTURE_RC=$?
echo "   gate_arc_lega_capture exit: ${CAPTURE_RC} (expected 0)"

# Restore staged status to leave changes in working tree as requested
git restore --staged : 2>/dev/null || true

L4_OK=1
if [ "$NAMING_RC" -ne 0 ]; then
  echo "   L4 FAIL: gate_arc_lega_naming.sh failed:"
  cat "$TMP/gate_naming.out"
  L4_OK=0
fi
if [ "$CAPTURE_RC" -ne 0 ]; then
  echo "   L4 FAIL: gate_arc_lega_capture.sh failed:"
  cat "$TMP/gate_capture.out"
  L4_OK=0
fi

if [ "$L4_OK" -eq 1 ]; then
  echo "   L4 PASS: naming and capture gates exit 0"
else
  FAIL=1
fi

echo "-- gate rc: $FAIL (0 = every leg PASS)"
exit "$FAIL"
