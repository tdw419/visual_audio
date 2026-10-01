# DRIVER ABI v1 — unified channel contract (Mailbox, Console, Block)

**Status:** FROZEN at CLAIM QUEUE item 27 (2026-09-26, builder af3e62239ce2).
**Version word:** `1` (major `1` = the driver-channel generation; this doc
version never reuses a number — a breaking change becomes DRIVER_ABI_v2.md
with a migration note). The gate is `tests/test_item27_driver_abi.py`.
**Change policy (inherited from BOX_ABI_v2):** any change to a FROZEN field
below requires a new major version and a migration note. Additive channels
or additive fields may bump the minor via a header note. The gate runs
green before landing, or the version bumps.

Scope of freeze: the **host-visible channel contracts** that drivers and
tasks use to move bytes in and out of glyph tasks. Three channels, one
suite:

| Channel | Frozen source | Implementation | Guest-visible arm |
|---|---|---|---|
| MAILBOX | BOX_ABI_v2 §4 | `tools/geos_emit.py` `encode_mailbox_word` | resident kernel (agent_resident.py) |
| CONSOLE | DTF-2 glass-TTY | `tools/glyph_text_console.py` | PRT byte stream (`GlyphCPUv2.output`) |
| BLOCK | VFS-1 transport | `tools/png_vfs.py` | 0x03/0x04/0x13 via `tools/glyph_vfs.py` attach |

---

## 1. MAILBOX channel (FROZEN)

The GH-22 one-word message, verbatim from BOX_ABI_v2 §4:

```
word = (cksum << 24) | (op << 8) | payload
  cksum = (op + payload) & 0xFF
  op: byte        payload: byte
  op 0x11 = post (argv); other ops reserved, assigned by minor-version bump
```

- Canonical check vector: `encode_mailbox_word(0x11, 0x2A) == 0x3B00112A`.
- Malformed operands (outside byte range) raise `EmitError` (E_MALFORMED)
  host-side — never a wrapped/garbage word.
- Arrival contract: seat posts payload @760, sets flag @742; the daemon
  claims (clears @742) and publishes receipt @761. No post ⇒ NO receipt.
- FROZEN constants: receipts `0x5EED0003` (queue drained), `0x5EED0004`
  (arrival serviced), `0x5EED0005` (fleet complete); fault verdict
  `0xFA026`; kernel status `0xCAFE0026`; ABI version `0x00020026` @952.
- Queue depth (740) and argv1 (752) are PLAIN words — not mailbox-wrapped.

## 2. CONSOLE channel (FROZEN)

The glass-TTY text band (`tools/glyph_text_console.py`):

- One cell = 8x16 px (IBM VGA font cell). Band = `rows*16` px tall,
  `cols*8` px wide. Defaults 8 rows × 40 cols.
- Exactly two legal colors per band: `on` (255,255,255) and `off`
  (0,0,0). Any third color makes strict decode RAISE — the channel
  refuses to echo a corrupted band, never silently degrades.
- Text → pixels → text is byte-exact: `decode_band(render_band())`
  returns the fed transcript (per-line rstrip; ring drops empty
  top-padding rows). Bottom-anchored ring, lines truncated to cols.
- A char missing from the font renders as `?` (documented replacement;
  coverage is 95 printable-ASCII glyphs since BK-19).

## 3. BLOCK channel (FROZEN)

The PNG disk transport (`tools/png_vfs.py`, VFS-1):

- The PNG is the TRANSPORT: pixels → Hilbert 1D byte offset → raw disk
  bytes. The raw disk IS ext2 (host `mke2fs`/`debugfs`/`e2fsck` produce
  and validate content; this module never parses ext2 structures).
- FROZEN 28-byte header at Hilbert byte offset 0 (pixel (0,0) starts the
  magic):

  | field | fmt | frozen value |
  |---|---|---|
  | magic | 8s | `b"PVFSIMG1"` |
  | version | H | `1` |
  | flags | H | `0` |
  | disk_sect | I | raw disk size in 512B sectors |
  | block_px | I | pixels per Hilbert block edge (power of two, ≥8) |
  | _pad | 8s | zero |

- Encoding: RGB24, 3 bytes per pixel (`pixel k` holds payload bytes
  `3k..3k+2`), row-major within a Hilbert block, blocks in `d2xy` order
  (Hacker's Delight curve, reference `tools/hilbert_reference_verify.py`).
- Loud failures (never silent zero-fill/truncation): corrupt magic →
  `PngVfsError` ("no png_vfs header magic"); unsupported version/flags;
  bad block_px; payload shorter than the header declares; wrap() of a
  non-512-multiple disk.
- Guest-visible arm (item-25, `tools/glyph_vfs.py`): attaching a GlyphVfs
  re-routes syscalls 0x03 (write) / 0x04 (read) / 0x13 (list) onto the
  ext2 image via a staged host-side overlay; `sync()` commits staging →
  ext2 → PNG. Guest paths are VFS-relative. Refusal = `-1`, loud print.

## 4. Unification leg (what "unified" means here)

One GlyphVfs attached to multiple spawned engines (the item-26 process
table, `vfs_shared=True`) is the CANONICAL multi-task pattern: task A's
0x03 write is byte-exactly task B's 0x04 read, with no host-FS file —
the block channel serves both sides through the staged overlay. Gate leg
U1 pins this; leg M3 pins the mailbox channel against the real baked
kernel; legs C1/C2 pin the console channel's round-trip.

## 5. What this freeze does NOT claim

- No WGSL twin parity: console render is host-side, the block channel is
  host e2progs — both out of the shader threat model (the 0x07/0x12/0x13
  normative-negative twin precedent). No new syscall number is introduced
  by this item, so the twin contract is untouched.
- No rate/latency/floor claims (nothing in the gate is timed).
- No real-silicon device model (GH-22's trusted-unproven boundary stands).
- Read isolation (LD unboxed) is unaffected and unclaimed (BOX_ABI_v2 §7).
