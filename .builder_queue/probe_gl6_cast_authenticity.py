#!/usr/bin/env python3
"""GL6-BUILD out-of-tree falsification probe (orchestrator, cron af3e62239ce2).

Purpose: the gate's L1/L2 legs only check STRUCTURE + ANCHOR PRESENCE, which a
hand-authored cast can satisfy. This probe proves the committed gate is not
satisfiable by authorship by exercising the same code path (check_cast) plus the
L3 comparison on (a) a fabricated cast and (b) a single-character mutation.

Run:  /usr/bin/python3 .builder_queue/probe_gl6_cast_authenticity.py
Writes nothing into the OSS repo; tmp files only.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

OSS = Path("/home/jericho/zion/worktrees/glyph-isa")
GATE = OSS / "tests" / "test_gl6_demo_cast.py"
COMMITTED = OSS / "docs" / "demo" / "gl6_bake_and_run.cast"
RECORDER = OSS / "tools" / "record_cast.py"

spec = importlib.util.spec_from_file_location("gl6_gate", GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

tmp = Path(tempfile.mkdtemp(prefix="gl6_probe_"))
results = []


def emit(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# --- 0. committed cast header + payload hash (provenance) ---
header, events, committed_payload = gate.check_cast(COMMITTED)
emit("committed.header", header.get("version") == 2 and header.get("exit_code") == 0,
     f"version={header.get('version')} exit_code={header.get('exit_code')} "
     f"dims={header.get('width')}x{header.get('height')} events={len(events)} "
     f"payload_bytes={len(committed_payload)} title={header.get('title')!r}")
import hashlib
print("committed.payload_sha256=" + hashlib.sha256(committed_payload.encode()).hexdigest())

# --- 1. real re-execution (fresh capture from the committed recorder) ---
fresh = tmp / "fresh.cast"
subprocess.run([sys.executable, str(RECORDER), "--out", str(fresh)],
               cwd=OSS, check=True, capture_output=True, text=True)
_, _, fresh_payload = gate.check_cast(fresh)
emit("L3.reexecution_reproduces_payload", fresh_payload == committed_payload,
     f"fresh_bytes={len(fresh_payload)} committed_bytes={len(committed_payload)} "
     f"identical={fresh_payload == committed_payload}")

# --- 2. FABRICATED cast: hand-authored, satisfies structure + all anchors ---
fabricated = tmp / "fabricated.cast"
fabricated_payload = (
    "$ ./glyphc build examples/01_hello.glyph -o /tmp/glyph_demo/01_hello.glyph.png\r\n"
    "\u2713 Baked 'examples/01_hello.glyph' -> '/tmp/glyph_demo/01_hello.glyph.png' (256x19 px, 64 cols)\r\n"
    "$ ./glyphc run /tmp/glyph_demo/01_hello.glyph.png\r\n"
    "OUTPUT: 42\r\n[HALTED] in 3 steps | r0=0 r10=42\r\n"
    "$ ./glyphc build examples/03_fibonacci.glyph -o /tmp/glyph_demo/03_fibonacci.glyph.png\r\n"
    "\u2713 Baked 'examples/03_fibonacci.glyph' -> '/tmp/glyph_demo/03_fibonacci.glyph.png' (256x19 px, 64 cols)\r\n"
    "$ ./glyphc run /tmp/glyph_demo/03_fibonacci.glyph.png\r\n"
    "OUTPUT: 13\r\n[HALTED] in 513 steps | r0=1 r10=13\r\n"
)
with open(fabricated, "w", encoding="utf-8") as f:
    f.write(json.dumps({"version": 2, "width": 80, "height": 24, "timestamp": 0,
                        "env": {"SHELL": "/bin/sh", "TERM": "xterm-256color"},
                        "title": "hand-authored", "exit_code": 0}) + "\n")
    f.write(json.dumps([0.0, "o", fabricated_payload]) + "\n")
    f.write(json.dumps([1.0, "o", ""]) + "\n")

# it MUST satisfy L1/L2 (structure + anchors) -- otherwise the probe is not testing what it claims
try:
    gate.check_cast(fabricated)
    passes_structure_and_anchors = True
    detail = "fabricated cast satisfies L1 structure + L2 anchors (as designed)"
except AssertionError as e:
    passes_structure_and_anchors = False
    detail = f"UNEXPECTED: fabricated cast failed L1/L2: {e}"
emit("fabrication.passes_L1_L2", passes_structure_and_anchors, detail)

# ...and MUST be caught by the L3 payload comparison
caught = fresh_payload != fabricated_payload
emit("L3.catches_fabrication", caught,
     f"payloads_differ={caught} (fabricated_bytes={len(fabricated_payload)}, "
     f"committed={len(committed_payload)}) -- a hand-authored cast cannot match a fresh real run")

# --- 3. single-character mutation inside a recorded payload ---
mutated = tmp / "mutated.cast"
raw = COMMITTED.read_text(encoding="utf-8")
mutated_raw = raw.replace("OUTPUT: 42", "OUTPUT: 92", 1)   # one character changed
assert mutated_raw != raw
mutated.write_text(mutated_raw, encoding="utf-8")
try:
    gate.check_cast(mutated)
    emit("L4.single_char_mutation_RED", False, "mutation passed the gate -- VACUOUS")
except AssertionError as e:
    emit("L4.single_char_mutation_RED", True, f"gate reported RED: {str(e)[:120]}")

# --- 4. provenance numbers for the receipt ---
_real_needed = None
print(f"\nprobe_tmp={tmp}")
n_fail = sum(1 for _, ok, _ in results if not ok)
print(f"SUMMARY: {len(results) - n_fail}/{len(results)} probes PASS")
sys.exit(1 if n_fail else 0)
