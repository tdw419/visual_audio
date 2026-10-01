# BOX ABI v2 (0x00020026) — FROZEN SPECIFICATION

**Status:** FROZEN at R2.1 (PRODUCT_ROADMAP.md, RATIFIED 1827f6cb).
**Version word:** `0x00020026` (major `0x0002` = the box-ABI generation, minor
`0x0026` = GH-26 resident-kernel lineage). The kernel writes this word to RAM
word **952** at boot; the conformance suite asserts it verbatim.
**Change policy:** this document is the contract. Any change to a FROZEN
field (word addresses, box semantics, mailbox format, syscall marshaling,
receipt values, version word) requires a new major version and a migration
note. Additive words (new mailbox ops, new reserved words) may bump the
minor. The conformance suite gates every future change to the kernel image.

Scope of freeze: the **resident-kernel box ABI** as landed (agent_resident.py
HEAD 68b11265, R1.1–R1.3 lineage) running on GlyphCPUv2
(glyph_dispatch/src/glyph/glyph_isa_v2.py). What the WGSL shader path does is
explicitly OUT of scope (known divergent — RECEIPT_R13_preference.md).

---

## 1. Register layout (architectural)

Glyph register file r0..r31, RV32I-mapped. The syscall convention fixes:

| Register | Role at SYSCALL | Note |
|---|---|---|
| r17 (a7) | syscall number | E-K2 marshals THIS, not the instruction imm (Bug 7) |
| r10 (a0) | argument 0 / return | SYSRET delivers SYS_A0 back into r10 |
| r11 (a1) | argument 1 | marshaled to SYS_A1 |

The SYSCALL instruction: if `KSYS_PC != 0` (E-K2 armed), the engine snapshots
the full register file (`_syscall_regs`), marshals r17/r10/r11 into
SYS_N/SYS_A0/SYS_A1, saves the resume PC (packed `(row<<16)|col`) into
SYSCALL_PC, drops to SUPER, jumps KSYS_PC. SYSRET restores the register file,
copies SYS_A0 → r10, re-enters USER, resumes at SYSCALL_PC. If KSYS_PC == 0,
the immediate-driven fallback runs (`_handle_syscall(imm)`) — legacy GeOS
numbers (glyph_isa_v2.py:1350 docstring) apply and are NOT part of this box
ABI freeze.

## 2. MMIO control block (BOX_MMIO_BASE = 0x8000, byte-addressed)

Kernel-programmed from SUPER mode; engine reads every step. Word index =
addr >> 2. FROZEN offsets:

| Offset | Name | Semantics |
|---|---|---|
| 0x00 | MODE_LATCH | kernel writes 1 (USER); engine one-shots on next JMPR/CALLR |
| 0x04 | KFAULT_PC | packed pixel PC of fault handler; 0 = disabled |
| 0x08 | KSYS_PC | packed pixel PC of syscall dispatcher; 0 = imm fallback |
| 0x0C/0x10 | BOX0_LO/HI | permitted byte range [lo,hi) for USER stores |
| 0x14/0x18 | BOX1_LO/HI | second permitted range |
| 0x1C | FAULT_ADDR | engine writes: faulting byte address |
| 0x20 | FAULT_PC | engine writes: packed PC of offending store |
| 0x24 | SYSCALL_PC | E-K2 saved resume PC |
| 0x28/0x2C | BOX2_LO/HI | third permitted range (tile-ABI window) |
| 0x30 | SYS_N | marshaled syscall number |
| 0x34 | SYS_A0 | arg0 in, result out (bytes written / status) |
| 0x38 | SYS_A1 | arg1 |
| 0x3C | KTICK_PC | tick handler PC; 0 = disabled |
| 0x40 | TIMER_COUNT | countdown steps remaining |
| 0x44 | TIMER_RELOAD | reload on expiry |
| 0x48 | TICK_PC | engine writes: interrupted PC |
| 0x4C | PAGE_TABLE | base word of page table in RAM; 0 = disabled |
| 0x160–0x16C | TILE_ROW/COL/H/W | GO-2 tile rect; TILE_H==0 ⇒ inert |

**Box predicate (E-K1), frozen semantics** (`_addr_in_box`,
glyph_isa_v2.py:740): a USER store is legal iff the byte address falls in
BOX0 ∪ BOX1 ∪ BOX2 (byte ranges, half-open, base-byte check for word stores)
or inside the armed tile rect. **An unset range (HI == 0) never matches** —
a partially configured box still confines. A violation suppresses the store,
writes FAULT_ADDR/FAULT_PC, and jumps KFAULT_PC (measured witness:
inter-box word 717 faulted at 0xb34). **LD is NOT box-checked** (write-only
isolation — honesty note carried from R1.2).

## 3. Memory map (RAM words, 16384-word space)

| Words | Region | FROZEN contents |
|---|---|---|
| 700–716 | BOX0 arena | argv@713, result@714, done@716 (in-box flag) |
| 717 | inter-box guard gap | combined done word (bits 0..3 = agents A..D). USER stores here always E-K1-reject; SUPER promotes in-box flags |
| 718–734 | BOX1 arena | argv@727, result@728, done@734, BOX1 result@733 (legacy single-agent) |
| 731 | fault word | 0xFA026 after a reaped E-K1 fault |
| 732 | ticks | preemption tick count |
| 735 | guard gap | — |
| 736–767 | BOX2 window | tile-ABI/mailbox words below |
| 740 | queue depth | plain count word (not GH-22 format) |
| 742 | arrival flag | 0 none, 1 post pending; daemon clears on claim |
| 744–747 | **RESERVED (this freeze)** | no image may write; future ABI growth |
| 750 | argv0 | GH-22 mailbox word (op 0x11 = post) |
| 752 | argv1 | plain verb/payload word |
| 754 | result0 | THE tile-ABI result word (single-agent legacy; A-exclusive in fleet) |
| 756–758 | queue result history | slot i → 756+i |
| 759 | queue receipt | 0x5EED0003 when drained |
| 760 | arrival payload | job in / result in place |
| 761 | arrival receipt | 0x5EED0004 when serviced |
| 765 | fleet receipt | 0x5EED0005 when fleet completes |
| 800–895 | agent mailbox (GH-13) | legacy, outside the boxes |
| 950 | status | 0xCAFE0026 = kernel OK (GH-26 tail) |
| 952 | ABI version | 0x00020026 — the freeze anchor |
| 1024–1279 | FS window | FS-pixel alias |
| 1536–1791 | page table base | GH-17; PTE tag contract per DEFECT-23-ROOT |
| 1568–1583 | syscall table | GH-18, 16 slots, sys_n 6..21 |
| 1600–1695 | tile rect | 24 instrs × 4 px (GH-9 window) |
| 3328–3583 | paged working memory | vpn 13, Sv39 window |

**Fleet arena map (per-leg arming discipline):** A [700,717) B [718,735)
C [736,752) D [752,768). In fleet mode the kernel SUPER-re-arms the box
registers to exactly the current agent's range before every KJMP; arming all
boxes simultaneously is the fleetnaive control (no isolation).

## 4. Mailbox protocol (GH-22 word format, FROZEN)

```
word = (cksum << 24) | (op << 8) | payload
  cksum = (op + payload) & 0xFF
  op: byte        payload: byte
  op 0x11 = post (argv); other ops reserved, assigned by minor-version bump
```

Canonical check vector: `encode_mailbox_word(0x11, 0x2A) == 0x3B00112A`.
Malformed operands (outside byte range) are rejected host-side (E_MALFORMED).
Queue depth (740) and argv1 (752) are PLAIN words by design — the consumer
loop needs the count/verb, not a wrapped mailbox word; do not "fix" this.

**Arrival contract (post-boot):** the seat posts payload @760, sets flag
@742 (host RAM write between step() calls — the mailbox ABI); the live
daemon polls (bounded, 2000), claims (clears the flag), triples in place
@760, publishes receipt @761. No post ⇒ NO receipt (forged-receipt RED leg
is part of the conformance suite).

**Receipt values are frozen:** 0x5EED0003 (queue drained), 0x5EED0004
(arrival serviced), 0x5EED0005 (fleet complete), 0xFA026 (E-K1 fault
verdict), 0xCAFE0026 (kernel status OK), ABI word 0x00020026.

## 5. Syscalls (E-K2 dispatcher, frozen for sys_n 6..21)

Fixed dispatcher slices: SYS 6 = copy task A's staged buffer (word 713) to
A's uart (710), return 4; SYS 7 = same for B (727→720). Table base word 1568,
16 slots (mask 15 → unsigned bounds check), image-pixel window pinned at
1312 — growing program text must never move it. Unknown syscall ⇒ 'E' (69)
marker, clean SYSRET. Marshaling per §1.

## 6. Conformance suite

`python3 -m pytest tests/test_box_abi_conformance.py -q` — all GREEN legs
must pass and both RED legs must demonstrably fail a corrupted expectation
set. The suite is the gate for ANY future change to the frozen surface: if
you touch agent_resident.py, baker.py, or glyph_isa_v2.py isolation code,
this suite runs green before landing, or the version word bumps with a
migration note.

## 7. What this freeze does NOT claim

- Read isolation (LD unboxed), simultaneous parallelism (time-multiplexed,
  one PC), WGSL shader-path parity (divergent: halt@153 fleet), an in-guest
  LLM supervisor (kernel dispatches; seat is host), any rate/floor claim
  (floors_authoritative.json measures SpatialRV32ICore.step — a different
  path), and Linux-boot syscall numbers outside the E-K2 dispatcher.
