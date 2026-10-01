# Glyph Syscall ABI Specification (Pillar 2.1)

Written against the ISA, not the Python engine: the contract is the
interface, engines are implementations. The Python engine
(`tools/glyph_isa_v2.py` `_handle_syscall`) is the reference
implementation; the WGSL twin (`tools/wgsl_glyph_isa_v2.py`) implements a
strict subset — the per-syscall twin status below is a normative part of
this spec and is enforced by
`tests/test_pillar21_abi_spec_rotguard.py` (the doc-rot guard), as are the
register/addr/storage/return claims. Cross-engine parity of the shared
subset is enforced separately by `tests/test_pillar23_parity_ci.py`.

**Machine-readable claims:** every `<!--ABI 0xNN ... -->` block is parsed
by the rot guard, which re-derives each claim from the engine sources and
the live engine. Changing a handler without updating its block turns the
gate RED. Fields: `name`, `args` (register contract), `storage` (which
memory view the DATA addresses live in: RAM / PIXEL / HOST), `returns`,
`twin` (IMPLEMENTED / STUB / UNIMPLEMENTED / BRIDGED), `twin_contract`
(NORMATIVE = the stated twin behavior IS the twin contract, asserted by the
rot guard; GAP = the stated twin behavior is a measured defect with a filed
ticket — callers must not rely on it, and the ticket's landing turns the
rot guard RED until the spec is re-synced).

**Conventions (all syscalls):**

- Arguments are read from the glyph register file: r1, r2, r3.
- The result is written to `SYSCALL rd`'s rd register by the dispatcher.
- **Storage homes:** DATA addresses point into RAM (`self.memory` /
  `ram_write`, LD/ST-readable), per the DEFECT-23-ROOT convention
  (LD/ST = RAM for data; the image is code, plus 0x11's sanctioned pixel
  copy and 0x10's container header). PATH/PIXEL addresses point into
  image/pixel space (`_mem_read`/`_mem_write`). HOST means the handler
  touches host files/processes via paths decoded from RAM (see `_read_path`).
- **No-crash OOB convention:** out-of-range RAM reads return 0;
  out-of-range writes truncate/drop (RAM never grows on a model-controlled
  address — the DEFECT-23 paged-dispatch arming-loop defect class). No
  handler ever faults on a bad address.
- **No errno set exists.** Handlers return -1 on failure with the reason
  printed to the host console; there is no in-machine errno register.
  (Pillar 2's exit criterion: an independent engine implements these
  return codes, not a hidden host error channel.)
- **Containment:** 0x07/0x12 targets must be regular files whose
  `realpath` is in `GLYPH_RUN_ALLOW` (env: colon-separated absolute
  paths); refusal returns -1. 0x13's directory must have its `realpath`
  at or under a `GLYPH_FS_ALLOW` root (same env model; unset = refuse
  everywhere — deny-by-default); refusal returns -1. 0x11's pixel copy
  is bounded by the caller's
  length only (it is kernel-class semantics, not user containment).
- **Reserved range:** 0x10–0xFF minus the implemented numbers is reserved
  for GeOS spatial services — the Python engine dispatches to the spatial
  registry MMIO bridge and returns 0; the WGSL twin returns 0 for 16u–255u
  minus the exclusions 18u (RUN2) and 19u (FILE_LIST), which fall to the
  unknown-syscall -1 path (both are NORMATIVE negative contracts).
- **Unknown syscalls return -1** on both engines (WGSL: `4294967295u`).

---

## 0x01 SYSCALL_WRITE

<!--ABI 0x01
name: SYSCALL_WRITE
args: r1=addr, r2=len
storage: RAM
returns: 0
twin: IMPLEMENTED
-->

Writes `r2` bytes from RAM at `r1` to the output stream. Out-of-range
bytes read as 0. Twin: own WGSL branch, reads its `ram` buffer into the
output ring (byte-identical to Python per the Pillar 2.3 corpus).

## 0x02 SYSCALL_READ

<!--ABI 0x02
name: SYSCALL_READ
args: r1=dest addr, r2=want
storage: RAM
returns: bytes actually read (0 on exhaustion)
twin: IMPLEMENTED
-->

Drains the harness-seeded input ring (INPUT_LEN/CURSOR/DATA at
BOX_MMIO_BASE+0x170/0x174/0x180, one byte per word, cap 64) into RAM at
`r1`, advancing the cursor by the count actually read, so "no more input"
(0 after prior drains) is distinguishable from "zero bytes requested" (0
with the cursor unmoved). Out-of-range dest truncates the read. Twin: own
WGSL branch, dest writes `ram_write` (2.2a residual, same commit both
engines).

## 0x03 SYSCALL_FILE_WRITE

<!--ABI 0x03
name: SYSCALL_FILE_WRITE
args: r1=path_addr, r2=data_addr, r3=len
storage: RAM
returns: 0, or -1 on failure
twin: STUB
twin_contract: NORMATIVE
-->

Writes `r3` bytes from RAM at `r2` to the host file at the NUL-terminated
path in RAM at `r1`. Invalid length (<0) returns -1. Twin: no-op stub
returning 0 — **sanctioned divergence (normative twin contract)**: the twin
runs in a compute shader with no host filesystem; a no-op that reports
success without touching the host FS is the twin's CONTRACT, not drift.
Host-side file effects are the Python engine's job (containment per the
rules above). If a future lane needs on-shader file persistence, that is a
new filed row with its own storage design — not silent growth of this stub.
Glyph-sh v2 exec (SE021, RUN/RUN2) runs on the Python engine; no on-shader
exec lane consumes FILE_WRITE today, so nothing is blocked by this contract.

## 0x04 SYSCALL_FILE_READ

<!--ABI 0x04
name: SYSCALL_FILE_READ
args: r1=path_addr, r2=dest_addr, r3=max_len
storage: RAM
returns: bytes actually read, or -1
twin: STUB
twin_contract: NORMATIVE
-->

Reads up to `r3` bytes of the host file at RAM path `r1` into RAM at
`r2`; missing file returns -1; out-of-range dest bytes are dropped.
Twin: no-op stub returning 0 — **sanctioned divergence (normative twin
contract)**, same reasoning as 0x03: no host FS exists on the shader path;
the stub writing nothing and reporting success is the twin's contract.
Callers porting read-side logic to the twin must source data from RAM
seeding / the input ring instead.

## 0x05 SYSCALL_EXIT

<!--ABI 0x05
name: SYSCALL_EXIT
args: r1=status
storage: HOST
returns: status
twin: IMPLEMENTED
-->

Stops the engine (`running = False`) and returns `r1`. Both engines stop
identically.

## 0x06 SYSCALL_DEBUG

<!--ABI 0x06
name: SYSCALL_DEBUG
args: r1=value
storage: HOST
returns: 0
twin: STUB
-->

Prints `r1` to the host console. Twin: no-op stub returning 0 (the value
is not observable on the twin; divergence by design).

## 0x07 SYSCALL_RUN

<!--ABI 0x07
name: SYSCALL_RUN
args: r1=path_addr
storage: HOST
returns: exit code, or -1
twin: UNIMPLEMENTED
twin_contract: NORMATIVE
-->

Spawns the executable at RAM path `r1` on the host with a 30 s timeout,
after containment (regular file, `realpath` ∈ `GLYPH_RUN_ALLOW`), and
returns its exit code. Twin: no branch — falls to the unknown-syscall path
and returns -1. **Normative twin contract: the twin's -1 IS the contract.**
Host process spawn is foreign to the shader threat model (containment —
the GLYPH_RUN_ALLOW allowlist, realpath checks, timeouts — is a Python/host
mechanism; a compute shader has no process table and must never gain one).
A twin -1 means "unavailable on this engine", deterministically, which is
exactly what a contained caller must see. Measured 2026-09-22 (both engines,
GPU twin): python=-1, twin=-1 — PARITY on the refusal path.

## 0x08 SYSCALL_AUDIO_OUT

<!--ABI 0x08
name: SYSCALL_AUDIO_OUT
args: r1=path_addr, r2=data_addr, r3=len
storage: RAM
returns: 0, or -1 on failure
twin: UNIMPLEMENTED
-->

Encodes `r3` bytes from RAM at `r2` through `Phy16Tone` and writes the
WAV to the path at RAM `r1`. Invalid length (<0) returns -1. Twin: no
branch — returns -1.

## 0x09 SYSCALL_AUDIO_IN

<!--ABI 0x09
name: SYSCALL_AUDIO_IN
args: r1=path_addr, r2=dest_addr, r3=max_len
storage: RAM
returns: bytes decoded, or -1
twin: UNIMPLEMENTED
-->

Decodes the WAV at path `r1` through `Phy16Tone` and writes up to `r3`
decoded bytes into RAM at `r2` (out-of-range dropped). Missing file
returns -1. Twin: no branch — returns -1.

## 0x10 SYSCALL_BOOT_LINUX

<!--ABI 0x10
name: SYSCALL_BOOT_LINUX
args: r1=container_addr, r2=flags
storage: RAM
returns: 0 if VAC2, else -1
twin: IMPLEMENTED
-->

Recognizes a VAC2 boot container: reads 4 RAM words at `r1` and accepts
iff bytes `[w0&0xFF, w1&0xFF, w2&0xFF, w3&0xFF] == "VAC2"` (one byte per
word, low byte first — the backlog-(d) data convention). Out-of-range
words read as 0 (signature check fails, -1; no crash). Recognition only —
no boot is performed. Migrated from PIXEL to RAM 2026-09-22 (backlog (d)
residual; header is DATA, not code). Twin: its own `16u` branch reads the
`ram` buffer via `ram_read` — RAM-seeded container accepted (0), image-only
seeding refused (-1), matching the CPU engine.

## 0x11 SYSCALL_STORE_CODE

<!--ABI 0x11
name: SYSCALL_STORE_CODE
args: r1=dest_addr, r2=src_addr, r3=len
storage: PIXEL
returns: 0, or -1 (len <= 0)
twin: BRIDGED
-->

Copies `r3` pixel words src→dest in PIXEL space (image is ROM for CODE —
DEFECT-27 excluded this handler from the backlog-(d) RAM migration
forever). **Twin divergence (documented): the twin's reserved-range
bridge returns 0 WITHOUT copying** — in-image self-patching is
Python-only today.

## 0x12 SYSCALL_RUN2

<!--ABI 0x12
name: SYSCALL_RUN2
args: r1=path_addr, r2=arg1_addr (0 = none), r3=arg2_addr (0 = none)
storage: HOST
returns: exit code, or -1
twin: UNIMPLEMENTED
twin_contract: NORMATIVE
-->

Like 0x07 but passes up to two RAM-path arguments to the child (SE021
glyph-on-glyph). Same containment, absolute-path spawn, 30 s timeout.
Twin: 18u is EXCLUDED from the GeOS reserved-range bridge (16u–255u;
TICKET_ITEM8 fix landed 2026-09-22), so it falls to the unknown-syscall
path and returns -1. **Normative twin contract: the twin's -1 IS the
contract** — identical reasoning to 0x07: host process spawn is foreign
to the shader threat model; a twin -1 means "unavailable on this
engine", deterministically. Correction history: this block first
falsely claimed `twin: UNIMPLEMENTED / returns -1` (rot guard blind to
the bridge), was re-truthed 2026-09-22 as a measured GAP
(python=-1, twin=0 via the bridge — false spawn-success), then the
bounded bridge exclusion landed the same day (TICKET_ITEM8_0x12_bridge_false_success.md),
returning the twin to the honest UNIMPLEMENTED / NEGATIVE contract.
Measured 2026-09-22 post-fix (both engines, GPU twin): python=-1,
twin=-1 (u32 4294967295) — PARITY on the refusal path.

## 0x13 SYSCALL_FILE_LIST

<!--ABI 0x13
name: SYSCALL_FILE_LIST
args: r1=dir_path_addr, r2=dest_addr, r3=max_bytes
storage: RAM
returns: entry count (NUL-separated names in dest), 0 for empty, or -1
twin: UNIMPLEMENTED
twin_contract: NORMATIVE
-->

Enumerates the host directory at RAM path `r1` and writes the entry
names NUL-separated into RAM at `r2`, capped at `r3` bytes (whole-name
truncation: a partial name is never emitted). Returns the ENTRY COUNT in
rd — 0 for an empty directory, -1 on refusal or failure. Containment
(BK-15, landed 2026-09-24): the directory's `realpath` must equal or sit
under one of the `GLYPH_FS_ALLOW` roots (colon-separated absolute paths,
the 0x07/0x12 `GLYPH_RUN_ALLOW` model); unset env = refuse everywhere
(deny-by-default — enumeration must not be cheaper to reach than RUN).
Dest is RAM (DEFECT-23-ROOT convention: listings are DATA); OOB dest
bytes drop. Sizes/mtimes are NOT in this contract (L2's `ls -l` upgrade
lands them later). Twin: no branch — 19u is EXCLUDED from the GeOS
reserved-range bridge (16u–255u, the 0x12 TICKET_ITEM8 precedent: the
unqualified bridge returned 0, a measured false listing-success), so it
falls to the unknown-syscall path and returns -1. **Normative twin
contract: the twin's -1 IS the contract** — host filesystem enumeration
is foreign to the shader threat model; a twin -1 means "unavailable on
this engine", deterministically. Measured 2026-09-24 (both engines, GPU
twin): python=entry count, twin=-1 — PARITY on the refusal path.

---

## Twin-status legend (normative)

- **IMPLEMENTED** — the twin has its own `syscall_num == Nu` branch with
  Python-matching semantics (parity pinned by the 2.3 corpus).
- **STUB** — the twin folds the number into the `3u/4u/6u` no-op group
  returning 0. Reports success, does nothing.
- **UNIMPLEMENTED** — no branch; falls to the twin's unknown-syscall
  handler returning -1.
- **BRIDGED** — the number falls in the twin's `16u..255u` group
  returning 0 (note: this includes 0x10/0x11, which Python treats as
  real handlers — the divergence is named per-syscall above).
