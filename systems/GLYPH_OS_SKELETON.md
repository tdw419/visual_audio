# SKELETON SIGNED OFF — Glyph OS, OS-Level Subsystems (Round 2)

**Date:** 2026-09-12
**Scope:** the four load-bearing subsystems that separate GeOS from a Linux-comparable OS
**Status:** Phase 1 (structure) + Phase 2 (architectural lock) COMPLETE — Phase 3 is builder work
**Pattern:** skeleton-driven development (`skeleton-driven-development` skill)
**Predecessor:** `systems/GLYPH_SPINE_SKELETON.md` (Round 1 — retention + write registry)

---

## 1. The honest framing

Round 1's skeleton was **one subsystem** (retention + write provenance), not an OS. This round addresses
the actual architectural gap. Measured against the roadmap, GeOS already has Linux-*shaped* subsystems
(processes GH-7, preemption GH-16, syscalls GH-6/18, POSIX shim GH-21, FS GH-8/20, drivers GH-22, libc GH-23,
shell+coreutils GH-10/BK-11, signals/join/pipes BK-3/4/10, boot GH-1..5, integrity BK-6).

Four load-bearing things Linux has and GeOS does **not** — each an *ownership* layer, which is why they were
hard to author mechanically:

| # | Gap | Why it is load-bearing |
|---|---|---|
| 1 | **Address space per process** | GH-17 gives ONE global page table. Linux gives each process its own + an ASID so switching is a word write. Today "isolation" is a contiguous box fence, not translation. |
| 2 | **Identity + capabilities** | GeOS has ONE bit (MODE_SUPER/MODE_USER). "User can write the FS" and "user can open a network endpoint" are indistinguishable, yet BK-13, GH-20, GH-22 and BK-6 all introduce privileged operations. |
| 3 | **Authoritative process table** | Spawn (GH-7), signals (BK-3), join (BK-4) each track state independently. Nothing can answer "is pid 5 alive?" or make illegal transitions impossible. |
| 4 | **Device/driver registry** | GH-22 defines the ABI but no table, so overlapping MMIO windows and double binds are undetectable. |

## 2. Boundary map

```
                        ┌───────────────────────────────────────────┐
                        │  geos_proctab   (the authority)           │
   GH-7 spawn ─────────>│   ProcessDescriptor  pid·asid·box·caps    │
   BK-4  exit  ────────>│   LEGAL_TRANSITIONS  [guard LIVE]         │
   BK-4  wait  ────────>│   Proctab.transition / reap (I2/I3/I4)    │
                        └───────┬─────────────────────┬─────────────┘
                                │ asid                │ caps
                                v                     v
        ┌───────────────────────────────┐   ┌──────────────────────────────┐
        │ geos_aspace                   │   │ geos_caps                    │
        │  AddressSpace  (satp word)    │   │  Identity(uid,gid,label)     │
        │  AsidAllocator (lowest-free)  │   │  gate() -> Decision(missing) │
        │  permits_access(pte,mode,st)  │   │  CapTable  (no amplification)│
        │  → PAGE_TABLE_ADDR 0x814C     │   │  CAP_DEV_MMIO ──┐            │
        └───────────────────────────────┘   └──────────────────┼───────────┘
                                                               v
                                            ┌──────────────────────────────┐
                                            │ geos_devtab                  │
                                            │  Devtab.probe/bind           │
                                            │  window_overlap [guard LIVE] │
                                            │  → box lo/hi words (ENGINE)  │
                                            └──────────────────────────────┘
```

Every arrow into the engine terminates at an MMIO word that already exists
(`PAGE_TABLE_ADDR` = 0x814C, box lo/hi at 0x0C..0x2C) — no new engine surface is invented.

## 3. Interface contracts (LOCKED)

### `geos_aspace` — per-process address spaces
| Symbol | Kind | Contract |
|---|---|---|
| `split_vaddr(vaddr) -> (vpn, offset)` | **IMPLEMENTED** | total; negative raises |
| `pte_pack(pfn, flags) -> int` | **IMPLEMENTED** | rejects unknown flag bits |
| `pte_unpack(pte) -> (pfn, flags)` | **IMPLEMENTED** | `pfn = pte >> 8` (engine-pinned) |
| `permits_access(pte, mode, is_store) -> bool` | **IMPLEMENTED** | mirrors engine lines 644/710: USER needs PTE_U; store needs PTE_W |
| `AsidAllocator.alloc/free/live` | **IMPLEMENTED** | lowest-free, deterministic; double-free raises |
| `AddressSpace.map/unmap/switch/clone_for_fork` | **STUB** | one-word switch via `satp_word`; no silent aliasing |

Pinned engine facts, cross-checked against `tools/glyph_isa_v2.py` source every run:
`PAGE_WORDS=256`, `PAGE_TABLE_BASE_WORD=1536`, `PTE_V/W/U/PIX/HILB = 0x1/0x2/0x4/0x8/0x10`,
`MODE_SUPER/USER = 0/1`.

### `geos_caps` — identity + capabilities
| Symbol | Kind | Contract |
|---|---|---|
| `cap_mask(required)` / `cap_names(mask)` | **IMPLEMENTED** | unknown bit raises; names sorted (canonical) |
| `cap_implies(held, required) -> bool` | **IMPLEMENTED** | I1: no transitivity; **CAP_ROOT is not a wildcard** |
| `gate(identity, held, required) -> Decision` | **IMPLEMENTED** | denial names the deficit mask — never bare `False` |
| `Identity(uid, gid, label)` | frozen | POSIX vocabulary for BK-11/BK-21; `label` for receipts/DEFECT-20 |
| `CapTable.grant/revoke/held` | **STUB** | revocation of CAP_ROOT requires `force=True`; no amplification |

Capability bits are grounded in real existing surfaces: `CAP_FS_WRITE` (GH-8/20), `CAP_FS_ADMIN`,
`CAP_SPAWN` (GH-7/9), `CAP_KILL` (BK-3), `CAP_NET` (BK-13), `CAP_DEV_MMIO` (GH-22),
`CAP_OBSERVE` (GH-24/26.5), `CAP_BOOT_VERIFY` (BK-6), `CAP_ROOT`.

### `geos_proctab` — process table + lifecycle
| Symbol | Kind | Contract |
|---|---|---|
| `LEGAL_TRANSITIONS` / `can_transition(src,dst)` | **IMPLEMENTED** | complete table; unknown state raises |
| `Proctab.transition(pid, dst)` | **LIVE GUARD** | raises `InvalidTransition` on any unlisted move |
| `PidAllocator.alloc/free/live` | **IMPLEMENTED** | lowest-free; release only after reap (I4) |
| `Proctab.mark_exited/reap` | **STUB** (guard live) | `ZOMBIE` holds the exit code; `reap` is the only path to `DEAD` |
| `Proctab.ready_set/children_of/zombies` | **IMPLEMENTED** | zombies excluded from the scheduler's ready set |
| `Proctab.admit` | **STUB** | validate + `NEW -> READY` |

States: `new, ready, running, waiting, zombie, dead`. `box ∈ {0,1,2}` — the engine's real boxes.

### `geos_devtab` — device table + driver registry
| Symbol | Kind | Contract |
|---|---|---|
| `device_id(vendor, cls)` / `device_vendor` / `device_class` | **IMPLEMENTED** | fixed widths; overflow raises (no silent aliasing) |
| `window_overlap(a,b)` / `window_ok(lo,hi)` | **IMPLEMENTED** | half-open ranges; empty/inverted raises; `window_ok` is a predicate |
| `match_score(driver, device) -> int` | **IMPLEMENTED** | 2 exact / 1 partial / -1 no match |
| `Driver` | frozen | `None` = wildcard field |
| `Devtab.bind` | **LIVE GUARD** | refuses overlap (I1) and double bind (I2) |
| `Devtab.register_device/grant_words` | **STUB** (grant validates) | emits box lo/hi word pair; out-of-aperture refuses |

## 4. Invariants

| Module | # | Invariant |
|---|---|---|
| aspace | I1 | translation is total: `offset < PAGE_WORDS` always |
| aspace | I2 | privilege checked at translation, not at the box fence (mirrors engine) |
| aspace | I3 | an ASID is an identity: two live spaces never share one |
| aspace | I4 | switching a space writes ONE word (`PAGE_TABLE_ADDR`) |
| aspace | I5 | no space destroyed while referenced (refcount) |
| caps | I1 | monotone lattice; no transitive or wildcard privilege |
| caps | I2 | denial is loud and names the missing cap |
| caps | I3 | `gate()` is pure — no mutation, no table access |
| caps | I4 | cap sets serialise canonically (sorted, hashable) |
| caps | I5 | root is explicit; uid 0 is not implicitly privileged |
| proctab | I1 | pid allocation deterministic (lowest-free) |
| proctab | I2 | every transition validated against the table |
| proctab | I3 | a zombie is not dead — it holds the exit code |
| proctab | I4 | `reap` is the only path `ZOMBIE -> DEAD`; pids not reused pre-reap |
| proctab | I5 | every process names an asid and a cap set |
| devtab | I1 | granted windows are disjoint |
| devtab | I2 | no double binding |
| devtab | I3 | matching + probe order deterministic |
| devtab | I4 | windows are word ranges inside the MMIO aperture; never clamped |
| devtab | I5 | binding requires CAP_DEV_MMIO (recorded, not assumed) |

## 5. Verification

```bash
python3 tools/geos_os_skel_verify.py      # exit 0
```

**Result this run: PASS — 85 legs green, exit 0.** Sections: compiles; stdlib-only (AST scan);
imports; declared interfaces; stub return types; **engine cross-check** (constants parsed out of
`tools/glyph_isa_v2.py` and compared — catches drift between skeleton and machine); discriminating pure core
(both directions for every check); determinism; loud refusal paths; non-mutation; failure-path liveness.

**Live guards (invariants, not I/O) are gated, not stubbed away:** `Proctab.transition`'s transition table,
`Devtab.bind`'s overlap/double-bind checks, `Devtab.grant_words`' aperture check.

**What is NOT proven — stated plainly:**
- Phase 3 I/O bodies (`AddressSpace.map/unmap/switch`, `CapTable.grant/revoke`, `Proctab.admit/mark_exited/reap`,
  `Devtab.register_device`). Stubbed **by design**: no integration tests until a plausible path to success exists.
- No kernel wiring: nothing yet writes a real page table or box word. The skeleton defines the contract only.
- **Semantic falsification probe not run.** The probe (mutate a module copy → expect RED) is blocked by this
  host's operator-consent guard on source-rewriting commands (attempted in Round 1; not retried here).
  Compensating evidence: every pure-core check is bidirectional and the guards raise on real illegal moves
  (ZOMBIE→RUNNING, double bind, overlapping window).

## 6. Phase 3 roadmap (builder fill-in order)

Each step independently gate-able; nothing depends on an unverified step. One step per builder run.

1. **`AddressSpace.map` / `unmap`** — write `entries[vpn]`; refuse silent remap of a live entry.
   Gate: map then read back; remap without unmap raises; vpn out of range raises.
2. **`AddressSpace.switch`** — write `satp_word` to `PAGE_TABLE_ADDR`. Gate: a fake MMIO word sink records
   exactly one write with the expected word.
3. **`AsidAllocator` + `AddressSpace.release` wiring** — refcount to zero frees the asid.
   Gate: release twice raises; asid reusable only after full release.
4. **`CapTable.grant/revoke/held`** — with the no-amplification rule and `force` for CAP_ROOT.
   Gate: granting an unheld cap raises; revoking CAP_ROOT without force raises.
5. **`Proctab.admit/mark_exited/reap`** — full lifecycle + asid release on reap.
   Gate: spawn→run→exit(42)→reap returns 42; pid and asid both reusable after reap.
6. **`Devtab.register_device` + duplicate rejection** — plus `grant_words` emission into a fake engine sink.
   Gate: duplicate dev name raises; grant words match the descriptor.
7. **Cross-module integration** — a `spawn()` that allocates pid+asid+box, grants caps, and binds a driver.
   Gate: full lifecycle with the CAP_DEV_MMIO requirement enforced end to end.
8. **Engine integration (separate round, own gate)** — wire `AddressSpace.switch` to the real engine via
   `PAGE_TABLE_ADDR`. This touches `tools/glyph_isa_v2.py` semantics and needs the arc regression green.

**Done means:** steps 1–7 each with RED→GREEN evidence, `geos_os_skel_verify.py` PASS, arc regression green,
and a receipt in `systems/RECEIPT_OS_SKELETON.md` naming what is not claimed.

## 7. Out of scope (explicit)

- **No network stack skeleton** — BK-13's `tools/glyph_gpt/net_stack.py` already exists and passed its gate;
  a second one would be duplication. `CAP_NET` gates the existing surface.
- **No paging/PTE redefinition** — GH-17/25 already define the page table and Hilbert frames; this round adds
  *per-process ownership*, not translation semantics.
- **No changes to any existing file.** All four modules are new and additive.
- **No users/groups administration, no filesystem permissions** — those build on `geos_caps` and need their own
  round.
- **No bare-metal story.** GeOS still runs on a host GPU/WASM; that gap is not addressed here.

## 8. Remaining Linux gap after this round (honest)

Once Phase 3 lands, the delta to "Linux-comparable" is: real privilege separation in the *filesystem*
(permissions/ownership), a production network stack, a device *ecosystem* (drivers for real hardware),
POSIX conformance breadth (BK-11 covers 5 coreutils), SMP/multi-core scheduling semantics, and bare-metal
execution. This round closes the four *ownership* gaps; those five remain, and they are each their own project.

## 9. Files

| File | Role |
|---|---|
| `tools/geos_aspace.py` | per-process address spaces (pure core implemented) |
| `tools/geos_caps.py` | identity + capabilities (pure core implemented) |
| `tools/geos_proctab.py` | process table + lifecycle (transition guard live) |
| `tools/geos_devtab.py` | device table + driver registry (bind guard live) |
| `tools/geos_os_skel_verify.py` | 85-leg structural harness, incl. engine cross-check |
| `systems/GLYPH_OS_SKELETON.md` | this document |
