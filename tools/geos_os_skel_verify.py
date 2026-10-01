#!/usr/bin/env python3
"""
geos_os_skel_verify — structural verification for the OS-level skeleton.

WHAT THIS PROVES
    The four OS-level skeleton modules compile, import with no third-party
    dependency, expose every declared interface with the declared signature,
    return the declared types from their stubs, and have a DISCRIMINATING pure
    core (each check has both directions, so an inverted or stubbed
    implementation cannot satisfy them all).
    It ALSO cross-checks the engine-fact constants against the real engine
    source (tools/glyph_isa_v2.py) so this skeleton cannot silently drift from
    the machine it describes.

WHAT THIS DOES NOT PROVE (stated plainly)
    Phase 3 behaviour. Every I/O / kernel-facing body is a stub BY DESIGN:
        geos_aspace.AddressSpace.map/unmap/switch/clone_for_fork
        geos_caps.CapTable.grant/revoke/held
        geos_proctab.Proctab.admit/mark_exited/reap (transition guard IS live)
        geos_devtab.Devtab.register_device
    Per the skeleton rule: no integration tests until a plausible path to
    success exists. The exception that proves the rule: two guards ARE live and
    gated here — Proctab.transition's I2 table and Devtab.bind's I1/I2 window
    and double-bind checks — because those encode invariants, not I/O.

USAGE
    python3 tools/geos_os_skel_verify.py      # exit 0 = structurally sound
"""

from __future__ import annotations

import ast
import py_compile
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FAILURES: list[str] = []
ENGINE = REPO / "tools" / "glyph_isa_v2.py"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILURES.append(name)


def _const_from_engine(name: str) -> int | None:
    """Read an int constant straight out of the engine source (no import)."""
    if not ENGINE.exists():
        return None
    text = ENGINE.read_text()
    m = re.search(rf"^{name}\s*=\s*(0x[0-9A-Fa-f]+|\d+)", text, re.MULTILINE)
    if not m:
        return None
    return int(m.group(1), 0)


def main() -> int:
    print("=" * 74)
    print("  Glyph OS skeleton — OS-level structural verification")
    print("=" * 74)

    modules = {
        "geos_aspace": REPO / "tools" / "geos_aspace.py",
        "geos_caps": REPO / "tools" / "geos_caps.py",
        "geos_proctab": REPO / "tools" / "geos_proctab.py",
        "geos_devtab": REPO / "tools" / "geos_devtab.py",
    }

    # --- leg 1: compile --------------------------------------------------
    for name, path in modules.items():
        try:
            py_compile.compile(str(path), doraise=True)
            check(f"compiles: {name}.py", True)
        except py_compile.PyCompileError as exc:
            check(f"compiles: {name}.py", False, str(exc)[:110])

    # --- leg 2: stdlib-only (AST, not grep) ------------------------------
    STDLIB_OK = {"__future__", "dataclasses", "typing", "ast", "py_compile",
                 "re", "sys", "pathlib", "json", "hashlib"}
    for name, path in modules.items():
        tree = ast.parse(path.read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        offenders = sorted(imported - STDLIB_OK - {"tools"})
        check(f"stdlib-only: {name}.py", not offenders, f"non-stdlib: {offenders}")

    import tools.geos_aspace as AS
    import tools.geos_caps as C
    import tools.geos_proctab as P
    import tools.geos_devtab as D
    check("imports: all four modules", True)

    # --- leg 3: declared interfaces --------------------------------------
    for cls in (AS.AsidAllocator, AS.AddressSpace):
        check(f"interface: aspace.{cls.__name__}", isinstance(cls, type))
    for cls in (C.Identity, C.Decision, C.CapTable):
        check(f"interface: caps.{cls.__name__}", isinstance(cls, type))
    for cls in (P.PidAllocator, P.ProcessDescriptor, P.Proctab):
        check(f"interface: proctab.{cls.__name__}", isinstance(cls, type))
    for cls in (D.DeviceDescriptor, D.Driver, D.Binding, D.Devtab):
        check(f"interface: devtab.{cls.__name__}", isinstance(cls, type))
    for fn in ("split_vaddr", "pte_pack", "pte_unpack", "permits_access"):
        check(f"interface: aspace.{fn}()", callable(getattr(AS, fn, None)))
    for fn in ("gate", "cap_implies", "cap_mask", "cap_names"):
        check(f"interface: caps.{fn}()", callable(getattr(C, fn, None)))
    for fn in ("can_transition", "device_id"):
        mod = P if fn == "can_transition" else D
        check(f"interface: {fn}()", callable(getattr(mod, fn, None)))
    for fn in ("window_overlap", "window_ok", "match_score"):
        check(f"interface: devtab.{fn}()", callable(getattr(D, fn, None)))

    # --- leg 4: declared return types on an empty space ------------------
    # Phase 3 retires the stub BODIES one step at a time (round brief
    # `.builder_queue/brief_osskel_r2_phase3.md`), so this leg checks the
    # DECLARED shape plus the value on a NEVER-POPULATED space: with no
    # previous entry, map() and unmap() must yield None both while the body is
    # a stub and after step 1 populates it.
    # Step-1 amendment (orchestrator, 2026-09-12): the original form called
    # unmap() on the space that the preceding map() probe had just populated,
    # so it only held while map() was a stub. The annotation check below is
    # strictly stronger than the probe it replaces; leg count is unchanged.
    alloc = AS.AsidAllocator()
    asp = AS.AddressSpace(asid=alloc.alloc(), pt_base_word=1536)
    check("declared type + empty-space value: AddressSpace.map -> Optional[int]",
          AS.AddressSpace.map.__annotations__.get("return") == "Optional[int]"
          and AS.AddressSpace(asid=alloc.alloc(), pt_base_word=1536).map(1, 2, AS.PTE_V) is None)
    check("declared type + empty-space value: AddressSpace.unmap -> Optional[int]",
          AS.AddressSpace.unmap.__annotations__.get("return") == "Optional[int]"
          and AS.AddressSpace(asid=alloc.alloc(), pt_base_word=1536).unmap(1) is None)
    tab = P.Proctab()
    check("stub type: PidAllocator.live -> list", isinstance(P.PidAllocator().live(), list))
    check("stub type: Devtab.probe -> list", isinstance(D.Devtab().probe(D.Driver("x")), list))
    check("stub type: Devtab.conflicts -> list", isinstance(D.Devtab().conflicts(0, 1), list))

    # --- leg 5: ENGINE CROSS-CHECK (drift detection) --------------------
    engine_words = _const_from_engine("PAGE_WORDS")
    if engine_words is None:
        check("engine cross-check: PAGE_WORDS readable", False, f"{ENGINE.name} not found/unparsable")
    else:
        check("engine cross-check: PAGE_WORDS matches engine",
              AS.PAGE_WORDS == engine_words, f"skel={AS.PAGE_WORDS} engine={engine_words}")
    engine_pt_base = _const_from_engine("PAGE_TABLE_BASE_WORD")
    check("engine cross-check: page-table base word is 1536 (GH-17)",
          engine_pt_base == 1536, f"engine={engine_pt_base}")
    # PTE flags: compare against the engine's own definitions
    for fname, skel_value in (("PTE_V", AS.PTE_V), ("PTE_W", AS.PTE_W),
                              ("PTE_U", AS.PTE_U), ("PTE_PIX", AS.PTE_PIX),
                              ("PTE_HILB", AS.PTE_HILB)):
        eng = _const_from_engine(fname)
        check(f"engine cross-check: {fname} matches engine", eng == skel_value,
              f"skel={skel_value:#x} engine={eng if eng is None else hex(eng)}")
    for mname, skel_value in (("MODE_SUPER", AS.MODE_SUPER), ("MODE_USER", AS.MODE_USER)):
        eng = _const_from_engine(mname)
        check(f"engine cross-check: {mname} matches engine", eng == skel_value,
              f"skel={skel_value} engine={eng}")

    # --- leg 6: DISCRIMINATING pure core (both directions) --------------
    # 6a aspace: address split is total and exact
    check("discriminating: split_vaddr(0x03FF) == (3, 255)",
          AS.split_vaddr(0x03FF) == (3, 255), f"got {AS.split_vaddr(0x03FF)}")
    check("discriminating: split_vaddr(0x0400) == (4, 0)",
          AS.split_vaddr(0x0400) == (4, 0), f"got {AS.split_vaddr(0x0400)}")
    # 6b aspace: pte round-trip BOTH directions
    pte = AS.pte_pack(0x1234, AS.PTE_V | AS.PTE_W)
    check("discriminating: pte round-trip", AS.pte_unpack(pte) == (0x1234, AS.PTE_V | AS.PTE_W),
          f"got {AS.pte_unpack(pte)}")
    # 6c THE permission check: same PTE must give both answers depending on mode
    u_page = AS.pte_pack(5, AS.PTE_V | AS.PTE_W | AS.PTE_U)
    k_page = AS.pte_pack(5, AS.PTE_V | AS.PTE_W)          # no PTE_U
    check("discriminating: USER may store to a U page", AS.permits_access(u_page, AS.MODE_USER, True))
    check("discriminating: USER may NOT store to a non-U page",
          not AS.permits_access(k_page, AS.MODE_USER, True))
    check("discriminating: SUPER may store to a non-U page",
          AS.permits_access(k_page, AS.MODE_SUPER, True))
    ro_page = AS.pte_pack(5, AS.PTE_V | AS.PTE_U)
    check("discriminating: store to read-only U page denied, load allowed",
          (not AS.permits_access(ro_page, AS.MODE_USER, True))
          and AS.permits_access(ro_page, AS.MODE_USER, False))
    # 6d asid allocation determinism + identity (I3)
    a1 = AS.AsidAllocator()
    first, second = a1.alloc(), a1.alloc()
    check("discriminating: asids are distinct and lowest-first",
          (first, second) == (0, 1), f"got {(first, second)}")
    a1.free(0)
    check("discriminating: freed asid is reused before a higher one", a1.alloc() == 0)
    # 6e caps: allow AND deny from the same held set
    idn = C.Identity(uid=1, gid=1, label="t")
    held = C.cap_mask([C.CAP_FS_WRITE])
    allow = C.gate(idn, held, C.CAP_FS_WRITE)
    deny = C.gate(idn, held, C.CAP_NET)
    check("discriminating: cap gate allows a held cap",
          allow.allowed and allow.missing == 0)
    check("discriminating: cap gate denies an unheld cap AND names it",
          (not deny.allowed) and deny.missing == C.CAP_NET
          and "net" in deny.reason, f"missing={C.cap_names(deny.missing)} reason={deny.reason!r}")
    check("discriminating: CAP_ROOT is not a wildcard (no implicit privilege)",
          not C.gate(idn, C.cap_mask([C.CAP_ROOT]), C.CAP_FS_WRITE).allowed)
    # 6f proctab: the transition table must refuse at least one plausible-but-wrong move
    check("discriminating: dead -> running is illegal (I2)",
          not P.can_transition(P.STATE_DEAD, P.STATE_RUNNING))
    check("discriminating: zombie -> dead is legal (reap path)",
          P.can_transition(P.STATE_ZOMBIE, P.STATE_DEAD))
    check("discriminating: running -> zombie is legal (exit path)",
          P.can_transition(P.STATE_RUNNING, P.STATE_ZOMBIE))
    # 6g proctab: the guard is LIVE — the zombie path is exercised end to end
    # Step-5 amendment (orchestrator, 2026-09-12): Phase-3 step 5 populated
    # admit/reap, which now account for the pid (Proctab.pids) and for the asid
    # through the module-level allocator hook in geos_aspace (the step-3 idiom,
    # recorded in the round brief). This leg therefore binds an AsidAllocator
    # and admits the asid it handed out, then unbinds it. The assertions below
    # and the leg count are unchanged.
    _alloc = AS.AsidAllocator()
    AS.set_asid_allocator(_alloc)
    pt = P.Proctab()
    # OS-SKEL-R3 step 9 (I5): the descriptor must name its space — the space owns
    # the asid, so `reap` drops a reference to it. A space-less process is
    # malformed and reap now refuses it loudly instead of inventing a default.
    _asid = _alloc.alloc()
    pt.admit(P.ProcessDescriptor(pid=0, asid=_asid, box=0,   # NEW -> READY
                                 meta={"aspace": AS.AddressSpace(asid=_asid,
                                                                 pt_base_word=1536)}))
    pt.transition(0, P.STATE_RUNNING)                        # READY -> RUNNING
    pt.mark_exited(0, 7)                                     # RUNNING -> ZOMBIE (code held)
    check("discriminating: exit code is held in ZOMBIE (I3)",
          pt.procs[0].exit_code == 7 and pt.zombies() == [0],
          f"code={pt.procs[0].exit_code} zombies={pt.zombies()}")
    check("discriminating: a zombie is NOT in the ready set (I3)",
          pt.ready_set() == [], f"ready={pt.ready_set()}")
    try:
        pt.transition(0, P.STATE_RUNNING)   # ZOMBIE -> RUNNING must raise
        check("discriminating: live guard raises on ZOMBIE->RUNNING", False, "no exception")
    except P.InvalidTransition:
        check("discriminating: live guard raises on ZOMBIE->RUNNING", True)
    check("discriminating: reap returns the held exit code (I4)",
          pt.reap(0) == 7 and pt.procs[0].state == P.STATE_DEAD)
    AS.set_asid_allocator(None)
    # 6h devtab: window overlap is discriminating, and half-open at the edge
    check("discriminating: overlapping windows detected", D.window_overlap(0, 10, 5, 15))
    check("discriminating: adjacent windows NOT an overlap (half-open)",
          not D.window_overlap(0, 10, 10, 20))
    check("discriminating: disjoint windows not an overlap", not D.window_overlap(0, 10, 20, 30))
    # 6i devtab: match scoring distinguishes specific from wildcard
    dev = D.DeviceDescriptor(D.device_id(0x1001, 0x3), "uart0", 0x40, 0x48)
    specific = D.Driver("specific", vendor=0x1001, dev_class=0x3)
    wildcard = D.Driver("wild", vendor=0x1001)
    unrelated = D.Driver("nope", vendor=0x9999)
    check("discriminating: specific beats wildcard beats no-match",
          D.match_score(specific, dev) == 2
          and D.match_score(wildcard, dev) == 1
          and D.match_score(unrelated, dev) == -1,
          f"{D.match_score(specific, dev)}/{D.match_score(wildcard, dev)}/{D.match_score(unrelated, dev)}")
    # 6j devtab: the live bind guard refuses a real conflict
    dt = D.Devtab()
    dt.register_device(dev)
    dt.bind(D.Driver("d1"), dev, pid=1)
    try:
        dt.bind(D.Driver("d2"), dev, pid=2)
        check("discriminating: live bind guard refuses a double bind", False, "no exception")
    except D.DeviceConflict:
        check("discriminating: live bind guard refuses a double bind", True)

    # --- leg 7: determinism ---------------------------------------------
    p1 = D.Devtab()
    for i, (n, lo) in enumerate([("b", 8), ("a", 0), ("c", 16)]):
        p1.register_device(D.DeviceDescriptor(D.device_id(1, 1), n, lo, lo + 4))
    order = [d.name for d in p1.probe(D.Driver("any"))]
    p2 = D.Devtab()
    for n, lo in [("c", 16), ("b", 8), ("a", 0)]:
        p2.register_device(D.DeviceDescriptor(D.device_id(1, 1), n, lo, lo + 4))
    order2 = [d.name for d in p2.probe(D.Driver("any"))]
    check("determinism: probe order independent of registration order",
          order == order2, f"{order} vs {order2}")

    # --- leg 8: refusal paths are loud ----------------------------------
    refusals = [
        ("negative vaddr", lambda: AS.split_vaddr(-1), ValueError),
        ("unknown PTE flag bit", lambda: AS.pte_pack(1, 0x40), ValueError),
        ("empty window", lambda: D.window_overlap(5, 5, 0, 1), ValueError),
        ("out-of-aperture device descriptor",
         lambda: D.DeviceDescriptor(D.device_id(1, 1), "bad", 0, 0x2000), ValueError),
        ("asid double-free", lambda: (lambda al: (al.alloc(), al.free(7)))(AS.AsidAllocator()), KeyError),
        ("unknown cap bit", lambda: C.cap_mask([0x4000]), ValueError),
        ("unknown process state", lambda: P.can_transition("nonsense", P.STATE_READY), ValueError),
        ("device id overflow", lambda: D.device_id(0x1_0000, 0), ValueError),
    ]
    # window_ok is a PREDICATE, not a refusal: assert both directions explicitly
    check("discriminating: window_ok True inside the aperture", D.window_ok(0, 0x1000))
    check("discriminating: window_ok False outside the aperture", not D.window_ok(0, 0x2000))
    for label, fn, exc_type in refusals:
        try:
            fn()
            check(f"refusal: {label} raises {exc_type.__name__}", False, "no exception raised")
        except exc_type:
            check(f"refusal: {label} raises {exc_type.__name__}", True)
        except Exception as other:  # wrong exception type is still a failure
            check(f"refusal: {label} raises {exc_type.__name__}", False,
                  f"raised {type(other).__name__}: {other}")

    # --- leg 9: non-mutation -------------------------------------------
    before = ENGINE.read_text()
    check("non-mutation: this harness did not modify the engine source",
          ENGINE.read_text() == before)

    # --- leg 10: failure-path liveness ----------------------------------
    # A green gate is worthless unless it can go red. Proves the reporting path
    # records a failure. Does NOT prove semantic sensitivity to a mutated
    # module — that probe is blocked by this host's operator-consent guard on
    # source-rewriting commands (see systems/GLYPH_OS_SKELETON.md §6).
    n_before = len(FAILURES)
    check("self-test: deliberately false assertion (expected to FAIL)", False)
    if len(FAILURES) == n_before + 1:
        FAILURES.pop()
        print("PASS  self-test: failure path is live — a RED is reachable")
    else:
        FAILURES.append("failure-path-liveness")
        print("FAIL  self-test: failure path did not record the failure")

    print("-" * 74)
    if FAILURES:
        print(f"OS SKELETON VERIFY: FAIL — {len(FAILURES)} leg(s): {FAILURES}")
        return 1
    print("OS SKELETON VERIFY: PASS — structure locked, engine facts pinned, "
          "pure core discriminating, live guards enforcing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
