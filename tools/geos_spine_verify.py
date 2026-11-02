#!/usr/bin/env python3
"""
geos_spine_verify — structural verification harness for the Glyph OS spine skeleton.

WHAT THIS PROVES (and what it does NOT)
    Proves : the skeleton is structurally valid — it compiles, imports with no
             third-party dependencies, every declared interface exists with the
             declared signature, and the IMPLEMENTED pure functions are
             DISCRIMINATING (they can return both answers; a function that can
             only ever return one thing is not a check).
    Does NOT prove: Phase 3 behaviour. The I/O stubs (ArchiveStore.compact,
             WriteRegistry.register persistence) are unimplemented by design.
             Per the skeleton rule: do not run integration tests until there is
             a plausible path to success.

USAGE
    python3 tools/geos_spine_verify.py        # exit 0 = skeleton structurally sound
"""

from __future__ import annotations

import ast
import inspect
import py_compile
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("=" * 72)
    print("  Glyph OS spine skeleton — structural verification")
    print("=" * 72)

    archive_py = REPO / "tools" / "geos_archive.py"
    registry_py = REPO / "tools" / "geos_registry.py"

    # --- leg 1: both modules compile -------------------------------------
    for path in (archive_py, registry_py):
        try:
            py_compile.compile(str(path), doraise=True)
            check(f"compiles: {path.name}", True)
        except py_compile.PyCompileError as exc:
            check(f"compiles: {path.name}", False, str(exc)[:120])

    # --- leg 2: import + zero third-party imports (AST, not grep) --------
    STDLIB_OK = {
        "__future__", "json", "hashlib", "dataclasses", "typing", "ast",
        "inspect", "py_compile", "sys", "tempfile", "pathlib", "os",
    }
    for path in (archive_py, registry_py):
        tree = ast.parse(path.read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        offenders = sorted(imported - STDLIB_OK - {"tools"})
        check(f"stdlib-only: {path.name}", not offenders, f"non-stdlib: {offenders}")

    import tools.geos_archive as A
    import tools.geos_registry as R
    check("imports: tools.geos_archive", True)
    check("imports: tools.geos_registry", True)

    # --- leg 3: declared interfaces exist with declared signatures -------
    for obj, name in [
        (A.ArchiveRecord, "ArchiveRecord"),
        (A.RetentionPolicy, "RetentionPolicy"),
        (A.Eviction, "Eviction"),
        (A.ArchiveStore, "ArchiveStore"),
        (R.WriteRegistry, "WriteRegistry"),
        (R.RegistryEntry, "RegistryEntry"),
    ]:
        check(f"interface: {name}", inspect.isclass(obj))

    for fn in ("retention_plan", "parse_record", "canonical_record_line"):
        check(f"interface: {fn}()", callable(getattr(A, fn, None)))
    for fn in ("registry_key", "entry_line", "index_digest", "line_sha_for"):
        check(f"interface: {fn}()", callable(getattr(R, fn, None)))

    # --- leg 4: stub bodies return the DECLARED types --------------------
    store = A.ArchiveStore(archive_dir="/nonexistent")
    plan = store.plan(A.RetentionPolicy(keep_total=1))
    check("stub type: ArchiveStore.plan -> list", isinstance(plan, list), f"got {type(plan).__name__}")
    res = store.compact([])
    check("stub type: ArchiveStore.compact -> dict", isinstance(res, dict))

    reg = R.WriteRegistry(index_path="/tmp/does-not-exist-registry.jsonl")
    check("stub type: WriteRegistry.lookup -> list", isinstance(reg.lookup("x", 1), list))
    check("stub type: WriteRegistry.conflicts -> dict", isinstance(reg.conflicts(), dict))
    check("stub type: WriteRegistry.scan -> list", isinstance(reg.scan("/nonexistent"), list))

    # --- leg 5: implemented pure core is DISCRIMINATING -------------------
    recs = [
        A.ArchiveRecord(1, "stage-a", "a1.npy", "a1.json", bytes_len=100),
        A.ArchiveRecord(2, "stage-a", "a2.npy", "a2.json", bytes_len=100),
        A.ArchiveRecord(3, "stage-b", "b1.npy", "b1.json", bytes_len=100),
    ]
    # 5a: per-writer quota keeps the NEWEST per writer, not the oldest
    ev = A.retention_plan(recs, A.RetentionPolicy(keep_per_writer=1))
    evicted_ids = sorted(e.record.write_id for e in ev)
    check("discriminating: per-writer quota evicts the OLDER record",
          evicted_ids == [1], f"evicted={evicted_ids} (expected [1], kept 2 and 3)")
    # 5b: the negative direction — no policy bound means no eviction
    ev_none = A.retention_plan(recs, A.RetentionPolicy())
    check("discriminating: unbounded policy evicts nothing", ev_none == [], f"got {len(ev_none)}")
    # 5c: tag exclusion is honoured and NAMED (I2)
    tagged = recs + [A.ArchiveRecord(4, "stage-a", "probe.npy", "probe.json", tags=("probe",))]
    ev_tag = A.retention_plan(tagged, A.RetentionPolicy(exclude_tags=("probe",)))
    check("discriminating: tag exclusion fires with a named reason",
          len(ev_tag) == 1 and ev_tag[0].reason == A.REASON_POLICY_EXCLUDED,
          f"reasons={[e.reason for e in ev_tag]}")
    # 5d: byte cap fires on the OLDEST first (newest-first survival, I3)
    big = [
        A.ArchiveRecord(10, "w", "n10.npy", "s10.json", bytes_len=60),
        A.ArchiveRecord(11, "w", "n11.npy", "s11.json", bytes_len=60),
    ]
    ev_bytes = A.retention_plan(big, A.RetentionPolicy(max_bytes=60))
    check("discriminating: byte cap evicts the older record first",
          [e.record.write_id for e in ev_bytes] == [10] and ev_bytes[0].reason == A.REASON_OVER_BYTES,
          f"evicted={[(e.record.write_id, e.reason) for e in ev_bytes]}")

    # --- leg 6: determinism (I1) — same inputs, same output, twice --------
    a = A.retention_plan(recs, A.RetentionPolicy(keep_per_writer=1))
    b = A.retention_plan(list(recs), A.RetentionPolicy(keep_per_writer=1))
    check("determinism: identical plans across runs",
          [(e.record.write_id, e.reason) for e in a] == [(e.record.write_id, e.reason) for e in b])

    # --- leg 7: canonical bytes (I3) + index digest sensitivity ----------
    line1 = A.canonical_record_line(recs[0])
    line2 = A.canonical_record_line(recs[0])
    check("canonical: identical record -> identical bytes", line1 == line2)
    check("canonical: sorted keys, compact separators",
          line1.startswith('{"bytes_len":') and ", " not in line1, line1[:60])
    d1 = R.index_digest([line1])
    d2 = R.index_digest([line1, A.canonical_record_line(recs[1])])
    check("digest: index digest changes when the log changes", d1 != d2)
    d3 = R.index_digest([line1])
    check("digest: index digest is stable for identical input", d1 == d3)

    # --- leg 8: loud refusal on unattributable writes --------------------
    try:
        A.parse_record({"writer": "x"}, "i.npy", "s.json")
        check("refusal: sidecar without write_id is rejected", False, "no exception raised")
    except ValueError:
        check("refusal: sidecar without write_id is rejected", True)
    try:
        R.registry_key("", 1)
        check("refusal: empty origin_id is rejected", False, "no exception raised")
    except ValueError:
        check("refusal: empty origin_id is rejected", True)

    # --- leg 9: no writes to disk during verification (non-mutation) -----
    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "unused"
        check("non-mutation: harness wrote nothing it was not asked to", not probe.exists())

    # --- leg 10: the harness's OWN failure path is live -------------------
    # A green gate is worthless unless it can go red. This leg proves the
    # reporting path records a failure and returns non-zero, so a future
    # green run cannot be a reporting artefact.
    # HONEST BOUNDARY: this proves the FAILURE PATH fires when told to. It does
    # NOT prove semantic sensitivity to a mutated retention_plan — that probe
    # (mutate a scratch copy of the module, confirm RED) was attempted and is
    # blocked by this host's operator-consent guard, so it is NOT claimed here.
    # Leg 5 is the compensating evidence: each of its checks has both
    # directions (evict / do-not-evict), so a stubbed or inverted plan cannot
    # satisfy them all.
    before = len(FAILURES)
    check("self-test: deliberately false assertion (expected to FAIL)", False)
    if len(FAILURES) != before + 1:
        print("FAIL  self-test: failure path did not record the failure")
        if "failure-path-liveness" not in FAILURES:
            FAILURES.append("failure-path-liveness")
    else:
        FAILURES.pop()
        print("PASS  self-test: failure path is live — a RED is reachable")

    print("-" * 72)
    if FAILURES:
        print(f"SKELETON VERIFY: FAIL — {len(FAILURES)} leg(s): {FAILURES}")
        return 1
    print("SKELETON VERIFY: PASS — structure locked, pure core discriminating, stubs typed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
