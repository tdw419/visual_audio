#!/usr/bin/env python3
"""Orchestrator's independent probes for DEFECT-24 (not agy's claims).

P1 discrimination on the REAL pre-fix source (git show HEAD:tests/test_gh18_syscall_abi.py),
P2 discrimination on the CURRENT source with only the live_smoke marker stripped,
P3 liveness of the socket.connect guard technique the deterministic leg relies on,
P4 byte-identity of the two test files before/after (probes must not mutate the tree).
"""
import hashlib
import pathlib
import socket
import subprocess
import sys

REPO = pathlib.Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))
from tests.test_arc_determinism_audit import find_unmarked_live_tests  # noqa: E402

CUR = REPO / "tests" / "test_gh18_syscall_abi.py"
GH26 = REPO / "tests" / "test_gh26_emit_admit.py"


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()


before = {p.name: md5(p) for p in (CUR, GH26)}

# ── P1: the REAL pre-fix file must be flagged ───────────────────────────
prefix_src = subprocess.run(
    ["git", "show", "HEAD:tests/test_gh18_syscall_abi.py"],
    cwd=str(REPO), capture_output=True, text=True, check=True).stdout
p1 = find_unmarked_live_tests(prefix_src, "REAL_PREFIX_gh18")
print(f"P1 real pre-fix violations: {p1}")
print(f"P1 VERDICT: {'PASS (discriminating)' if p1 == ['REAL_PREFIX_gh18::test_gh18_admit_syscall_via_ingest_end_to_end'] else 'FAIL'}")

# ── P2: current source, marker stripped -> must be flagged ──────────────
cur_src = CUR.read_text()
stripped = cur_src.replace(
    "@pytest.mark.live_smoke\ndef test_gh18_admit_syscall_live_draft_smoke",
    "def test_gh18_admit_syscall_live_draft_smoke")
assert stripped != cur_src, "marker line not found — probe is stale"
p2 = find_unmarked_live_tests(stripped, "MUTATED_gh18")
print(f"P2 mutated-current violations: {p2}")
print(f"P2 VERDICT: {'PASS (discriminating)' if p2 == ['MUTATED_gh18::test_gh18_admit_syscall_live_draft_smoke'] else 'FAIL'}")
print(f"P2 control (unmutated current): {find_unmarked_live_tests(cur_src, 'CURRENT_gh18')}")

# ── P3: the connect-guard technique actually intercepts ─────────────────
attempts = []


def _guard(self, address, *a, **k):
    attempts.append(address)
    raise AssertionError(f"guard fired for {address}")


orig = socket.socket.connect
socket.socket.connect = _guard
fired = None
try:
    socket.create_connection(("localhost", 11434), timeout=3)
    fired = False
except AssertionError:
    fired = True
except Exception as e:  # noqa: BLE001
    fired = f"other:{type(e).__name__}"
finally:
    socket.socket.connect = orig
print(f"P3 guard attempts={attempts} fired={fired}")
print(f"P3 VERDICT: {'PASS (guard is live)' if fired is True else 'FAIL'}")

# ── P4: no mutation ─────────────────────────────────────────────────────
after = {p.name: md5(p) for p in (CUR, GH26)}
print(f"P4 md5 before={before}")
print(f"P4 md5 after ={after}")
print(f"P4 VERDICT: {'PASS (byte-identical)' if before == after else 'FAIL'}")
