# SCOPING — Memory-View Unification (roadmap item (d), Jericho request 2026-09-16)

**Author:** builder orchestrator cron `af3e62239ce2`, 2026-09-16.
**Scope of this document:** measured inventory only — no engine code changed.
**Method:** every claim below was read from the handler/opcode code at HEAD
`31d1328` (+ the sibling session's staged delta in `tools/glyph_isa_v2.py`,
mtime 07:29, which contains the `_read_path` view-merge and SYSCALL 0x12;
that delta is the sibling's in-flight work and was NOT modified).

## 1. The measured pain chain (why this item exists)

Three spaces exist and only one is visible to source:

| Space | Storage | Reached by |
|---|---|---|
| RAM array | `GlyphCPUv2.memory` (1024+ words, growable) | unpaged `LD`/`ST` (`glyph_isa_v2.py:892-895`, `:1010-1035`), transpiled `SW`/`LW` (they lower to glyph `ST`/`LD`, `rv64i_to_glyph.py:853-880`) |
| Image pixels | the saved ndarray (program + FS + wrap target) | `_mem_read`/`_mem_write` (`:693-707`) — all syscall data args, `PUSH`/`POP`/`CALL`/`RET` (`:1060-1086`), paged `PTE_PIX`/`PTE_HILB` walks |
| FS window [1024,1280) | the ONLY alias zone: `_fs_pix_read/_fs_pix_write` (`:668-691`) | unpaged `LD`/`ST` when `fs_pix_enabled`; also `_mem_read/_mem_write` at same addresses |

The GH-8b window (`glyph_isa_v2.py:668-669`) was built as the sanctioned
alias. Everything outside it diverges silently: an `ST` writes RAM, a syscall
read of the same address reads pixels (`_read_path` pre-fix: SE021's
"not a regular file" on an existing file), and neither direction faults.

## 2. Per-syscall space inventory (all measured from `_handle_syscall`, `glyph_isa_v2.py:1300-1600`)

| Syscall | Arg | Space accessed (pre-sibling-delta HEAD) | Notes |
|---|---|---|---|
| 0x01 WRITE | data r1 | **image** (`_mem_read`, `:1353-1358`) | program must stage output bytes in image space — inside [1024,1280) in practice, else ST-written bytes are invisible |
| 0x02 READ | buf r1 | **RAM** (`self.memory`, `:1204` region, `:1363+`) | the one syscall already fixed to RAM; LD-readable |
| 0x03 FILE_WRITE | path r1 / data r2 | path: view-merged (sibling delta); data: **image** (`:1417`) | |
| 0x04 FILE_READ | path r1 / dest r2 | path: view-merged; dest: **image** (`_mem_write`, `:1437`) | this is the static check's `IMAGE_SPACE_WRITE_SYSCALLS` member |
| 0x05 EXIT | — | registers only | no space |
| 0x06 DEBUG | r1 | value, no space | |
| 0x07 RUN | path r1 | path: view-merged (sibling delta) | pre-delta: image-only reads — SE021's empty-path defect |
| 0x08 AUDIO_OUT | data r2 | **image** (`:1498+13`) | same class as 0x03 |
| 0x09 AUDIO_IN | dest r2 | **image** (`_mem_write`) | static-check member |
| 0x10 BOOT_LINUX | container r1 | **image** (`_mem_read`, `:1528+`) | 2-word header read |
| 0x11 STORE_CODE | src r2 / dest r1 | **image** both (`_mem_read/_mem_write`, `:1546+`) | static-check member |
| 0x12 RUN2 | paths r1/r2/r3 | view-merged via `_read_path` (sibling delta, `:1559+`) | new, staged, uncommitted |

**Pre-sibling-delta tally: 8 of 11 space-taking syscalls address the IMAGE;
1 addresses RAM (0x02); paths were image-only and are being view-merged by
the sibling in flight.** The view-merge (`glyph_isa_v2.py:1324-1347`, staged)
is a per-syscall patch over the root asymmetry — it fixes path reads only;
data/dest buffers (0x01/0x03/0x04/0x08/0x09/0x11) remain image-space.

## 3. Engine opcode asymmetries (CPU engine, measured)

1. **LD vs ST box discipline:** `ST` traps E-K1 on out-of-box USER stores
   (`:1010`); `LD` has NO equivalent — a USER `LD` of any address succeeds
   (`:892-895`). Loads are unchecked by design; only stores fault.
2. **Stack lives in image space; transpiled C stack lives in RAM.** Glyph
   `PUSH`/`POP`/`CALL`/`RET` go through `_mem_write`/`_mem_read` (`:1060-1086`)
   → image. Transpiled GCC `SW sp` lowers to glyph `ST` (`rv64i_to_glyph.py:866-880`)
   → RAM. Two different stacks coexist; a program mixing native PUSH and
   transpiled SW-to-sp never sees the other's frames.
3. **Out-of-RAM LD wraps onto pixels** (ENG-3, `:897-902`); out-of-RAM ST
   **faults** (`:1036-1059`). Same address class, opposite outcomes.
4. **PNG persistence is window-only:** `_fs_pix_write` mirrors to
   `memory[]` in-window (`:686-691`); RAM writes outside [1024,1280) vanish
   on image save/reboot. The image is the persisted truth; RAM is per-run scratch.

## 4. WGSL twin delta (measured — this is the load-bearing finding)

`tools/wgsl_glyph_isa_v2.py` and
`glyph_dispatch/src/glyph/wgsl_glyph_isa_v2.py` are md5-IDENTICAL today
(verified this run). In them:

- `mem_read`/`mem_write` (`:126-136`) = image pixels ONLY. **No FS-window
  aliasing, no RAM array** — the docstring (`:88`) states the image is both
  program and scratch.
- `walk_ld`/`walk_st` (`:240-303`) add `box_mmio` for the reserved MMIO block
  (the WGSL's only persistent store there, BK-2 fix `:246-256`).
- Legacy syscall table (`glyph_dispatch copy :493-528`): FILE_WRITE/READ and
  DEBUG stub to `rd=0`; WRITE/READ loop over the same image-only `mem_read/
  mem_write`. There is no `_read_path`, no host FS, no view-merge — by design
  (no host filesystem on GPU lanes).

**Consequence: the two engines already run different memory models.** The CPU
reads RAM-first outside the FS window; WGSL reads pixels everywhere. Every
parity gate (GH-4, BK-2, BK-12) holds only because fixtures either stay
inside [1024,1280), use pixel-space staging, or compare end-state via PNG
round-trip where window writes dominate. **Any unification that changes CPU
space semantics must re-derive every parity gate's staging assumptions.**

## 5. Transpiler impact (measured)

- `LW`/`LD`/`SW`/`SD` → glyph `LD`/`ST` → **RAM** (`rv64i_to_glyph.py:853-880`,
  with the `byte_to_word_mem >>2` and DEFECT-16c LBU/LHU scratch lanes).
- `EBREAK` → glyph `SYSCALL r10` (`:1250-1258`): syscall data args are then
  interpreted in IMAGE space by the handlers above.
- Net: **transpiled C has no way to name image space.** Every program that
  does file/audio I/O must hand-stage buffers into [1024,1280) with raw
  `LDI`/`ST` — exactly the echo-app layout constraint
  (`tests/test_glyph_app_echo.py:31-42`, `assert read_addr+len(message) < 1280`).
  The 256-word window is therefore a hard I/O budget per program today.

## 6. Blast-radius read (the 51-file JZ lesson applied)

Surface touching the dual-space semantics:

- Engine: `tools/glyph_isa_v2.py` `_mem_*`, `_fs_pix_*`, `_handle_syscall`,
  LD/ST/PUSH/POP/CALL/RET arms (~200 lines of the 1,664-line file).
- WGSL twin: 2 md5-identical copies (`tools/` + `glyph_dispatch/src/glyph/`).
- Baker reserved ranges: `tools/glyph_gpt/baker.py:51` (window entry in
  `_BAKER_RESERVED_RANGES`) and the GH-9 protected-set at `:2365`.
- Static assembler check: `IMAGE_SPACE_WRITE_SYSCALLS` + FS-window exemption
  (`glyph_isa_v2.py:357`, `:409-425`) — becomes obsolete under (A), simplifies
  under (B).
- Test surface: **16 test files** reference the syscall/FS window surface
  (grep census this run): gh8/gh8c/gh20, bk2/bk8/bk12, syscall_handlers,
  syscall_integration, glyph_file_io/audio_io/app_echo/app_glyph_on_glyph/
  app_shell_dispatch/app_voice, orchestrator_speak_to_driver,
  ram_pixel_space_check, arc prefix fixture. ~34 test functions in the
  six core files alone (counted: 2+1+10+7+7+7).

## 7. Option analysis (decision Jericho's; cost estimates are structural, not measured)

### Option A — unify: RAM is THE data space, image is ROM
- Mechanism: syscall data args switch to `self.memory[...]`; `_read_path`
  view-merge retires; FS window stays as the only sanctioned image alias for
  PNG persistence; assembler `IMAGE_SPACE_WRITE_SYSCALLS` table deleted
  (everything is RAM — the static check's whole premise disappears).
- Must touch: all 11 handler arms; PUSH/POP/CALL/RET stack decision (move to
  RAM or leave as the one image-space citizen); WGSL twin (needs a RAM
  analogue — a second storage buffer — or explicit statement that WGSL lanes
  diverge here); `walk_ld/walk_st` staging; ~16 test files re-staged from
  pixel seeds to RAM seeds (`tests/test_syscall_handlers.py` was JUST
  re-authored to pixel space for DEFECT-27 — would be re-re-authored again).
- Risks: DEFECT-27's ruling (store-code = PIXEL space, `0x11` copies pixels)
  must be preserved — image is ROM for CODE but 0x11 writes code pixels; the
  ruling's mechanism survives but its wording needs a (A)-compat addendum.
  PNG round-trip story stays coherent ONLY through the window — I/O data
  >256 words per program still has no persistence path (today's limit is
  unchanged, not fixed, by (A)).
- Cost shape: wide (engine + twin + ~16 files) but each site is mechanical.

### Option B — split syntax: `LD`/`ST` (RAM) vs `LDIMG`/`STIMG` (image)
- Mechanism: two opcode names (or a modifier); existing `LD`/`ST` keep RAM;
  syscalls that take data args get their space from the arg's provenance or
  the syscall is duplicated (e.g. `FILE_WRITE` stays image-arg; a new
  `FILE_WRITE_RAM`… grows the table) — OR simpler: keep syscall arg spaces
  as-is and only make PROGRAM-side access explicit, so mismatches are
  statically checkable without the FS-window exemption heuristic.
- Must touch: assembler (new mnemonics + encoding), transpiler (emit the RAM
  forms — it already does; image forms only where I/O staging happens),
  WGSL twin (add the two opcodes or map them to existing mem_read/mem_write),
  baker opcode-color table, static check (strengthenable: no exemption needed,
  both spaces statically nameable).
- Risks: dual-space mental model is permanent (the roadmap's own words);
  syscall arg space STILL implicit (the 0x01-stages-in-image problem isn't
  fixed for the author — only made nameable); additive so 51-file-style
  re-verification cost is near zero for existing programs.
- Cost shape: narrow and additive, but leaves the root divergence (syscall
  arg spaces) in place.

### Honest structural recommendation (not a ruling)
The pain chain item (d) cites (SE021 stack, echo-app false positive, dest
windows in-window) is mostly SYSCALL-arg-space pain, not opcode-space pain.
Option B alone does not fix it. The minimal root fix is actually narrower
than (A): **make syscall data args read/write RAM (the 0x02 precedent),
keep 0x11 STORE_CODE pixel-space per DEFECT-27, retire the view-merge.**
That is "(A) scoped to handlers only" — WGSL's legacy table already stubs
the affected syscalls, so the twin delta is bounded to the E-K2 dispatcher
path, and the pixel-seeded test fixtures stay valid only where they test
0x11/0x10. A full (A) (stack migration etc.) can follow or never; the
handler-scoped version removes every SE021-class defect. The 256-word
persistence budget is orthogonal to both and would need its own item
(window grow or a page-backed FS) — flagging, not scoping, it here.

## 8. What this scoping pass did NOT do

- No engine/twin/baker code modified (tree verified: only sibling's staged
  delta + pre-existing dirty files present).
- No WGSL run (no GPU leg); WGSL claims are from reading the shader source.
- Test blast radius is a census (16 files named), not a re-run.
- Cost estimates are structural (sites-to-touch), not measured hours.
- GH-20 fs_v2 internals not re-read; if fs_v2 moved syscall arg spaces
  further, the inventory in §2 may need a delta — §2 reflects
  `tools/glyph_isa_v2.py` as staged at 07:29 2026-09-16.
- The sibling session's view-merge/RUN2 delta is described but not judged;
  if it lands first, §2's tally changes (paths become RAM-first-readable)
  but §4's finding (WGSL has no view-merge) and §7's recommendation stand.
