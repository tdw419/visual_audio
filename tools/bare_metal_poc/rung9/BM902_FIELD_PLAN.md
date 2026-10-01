# BM902_FIELD_PLAN.md — TASK_BM902 step 1 (committed BEFORE capture legs)

**Purpose:** per-field classification of the 4KB `boot_params` struct, marking
each field `oracle-value / ours-expected / loader-specific?`. This table is
DATA for the gate: the differ's whitelist of loader-specific offsets is
generated from the `MUST-MATCH` rows here, and L1 fails on any differing byte
whose offset is not in the whitelist. Written before any stage2 handoff code
exists, per the brief (`brief_bm902_stage2_handoff.md`, method step 3).

**Oracle of record:** `oracle_zp_leg0.bin` = `oracle_zp_leg1.bin`
(sha256 `c3120d8e…`, unchanged), captured at the kernel's first protected-mode
instruction from the real chain SeaBIOS→isolinux→bzImage. Registers and
cmdline classification follow the same table format at the bottom.

**Honesty note (measured this run):** `ORACLE_BOOT_PARAMS.md` says "any field
not listed here measured 0x00" — that is TRUE only for the struct's offset
range ≥ 0x1e8 (the protocol's own fields). The dump's **low region 0x000–0x1e7
is NOT zero** in the oracle: it carries the real-mode kernel's setup
leftovers (screen_info incl. `"QEMU Monitor"` DDC/EDID bytes at 0x1b1,
vidmode 0x03 at 0x006/0x00a, alt_mem_k 0x0423 at 0x003…) plus an EDD "GSIC"
signature at 0x06c. The protocol defines these as loader/kernel scratch that
the protected-mode kernel does not read via boot_params (it reads screen_info
fields it needs from the zero page in early setup — but our stage2's contract
here is the BM901 DIFFERENTIAL BAR, not full kernel semantics). Classification
below therefore treats 0x000–0x1e7 as **STAGE2-CHOICE** (documented, counted,
non-whitelisted-by-default): we will zero them and the diff will show exactly
that region — as named diffs, never as hangs. If the gate later needs that
region byte-identical, that is a DESIGN escalation to Jericho (would mean
stage2 must replay screen_info), not a silent whitelist widening.

## Field plan — zeropage high region (offsets ≥ 0x1e8, protocol-defined)

Legend: `MUST-MATCH` = diff must be byte-equal or gate RED;
`LOADER-SPECIFIC` = expected to differ, whitelisted with cause;
`STAGE2-CHOICE` = we set a defined value, whitelisted with cause.

| Offset | Size | Field | Oracle ×2 | Ours (stage2) | Class | Cause if different |
|---|---|---|---|---|---|---|
| 0x1e8 | 1 | e820_entries | 0x07 | 0x07 | MUST-MATCH | stage2 copies SeaBIOS e820 (we consume the same QEMU fw) |
| 0x1e9 | 1 | eddbuf_entries | 0x00 | 0x00 | MUST-MATCH | — |
| 0x1ea | 1 | edd_mbr_sig_buf_entries | 0x00 | 0x00 | MUST-MATCH | — |
| 0x1f1 | 1 | setup_sects | 0x1b (27) | 0x1b | MUST-MATCH | read from bzImage |
| 0x1f2 | 2 | root_flags | 0x0001 (measured: `01 00`) | 0x0000 or same | LIKELY-MATCH | loader-set; harmless to reproduce |
| 0x1f4 | 4 | syssize | 0x0004152a paras (4,280,976 B) | same | MUST-MATCH | read from bzImage |
| 0x1f8 | 4 | ram_size | **0xffff0000** (measured: `00 00 ff ff`) | 0x00000000 | LOADER-SPECIFIC | isolinux real-mode scratch leftover; protocol: loader-set, kernel re-derives memory from e820 |
| 0x1fa | 2 | vid_mode | 0xffff (= "normal", measured: `ff ff`) | 0xffff | LIKELY-MATCH | we can honestly set normal |
| 0x1fc | 2 | root_dev | 0x0200 (measured: `00 02`) | 0x0000 | LOADER-SPECIFIC | isolinux scratch; unused for PM handoff |
| 0x1fe | 2 | boot_flag | 0xaa55 | 0xaa55 | MUST-MATCH | mandatory |
| 0x202 | 4 | header | "HdrS" | "HdrS" | MUST-MATCH | mandatory |
| 0x206 | 2 | version | 0x020d | 0x020d | MUST-MATCH | read from bzImage |
| 0x208 | 4 | realmode_swtch | 0x0 | 0x0 | MUST-MATCH | default |
| 0x20c | 4 | start_sys_seg | 0x34201000 (non-zero) | 0x0000 (a20 short-jump path unused) | LOADER-SPECIFIC | isolinux scratch; spec: obsolete/undefined for protocol ≥2.02 when loadflags&0x80 |
| 0x210 | 1 | type_of_loader | 0x33 (isolinux chainload 3<<4|3) | **0xff** (or 0xE0-class "special"; FINAL VALUE FIXED AT FIELD-PLAN REVIEW, see open Q1) | LOADER-SPECIFIC | the defining loader-specific field; kernel accepts 0xff per protocol ("undefined") |
| 0x211 | 1 | loadflags | 0x81 (LOADED_HIGH\|CAN_USE_HEAP) | 0x81 if we load high + no initrd (bit0 stays 0 unless we ship one); FINAL AT Q1 | LIKELY-MATCH (verify at build) | loadflags is OURS to set correctly: 0x01 LOADED_HIGH must match since code32_start=0x100000 implies high load; CAN_USE_HEAP bit is loader-honesty, we set it with heap_end_ptr set |
| 0x212 | 2 | setup_move_size | 0x8000 | 0x0000 | LOADER-SPECIFIC | only meaningful when loading low (loadflags bit0=0); we load high |
| 0x214 | 4 | code32_start | 0x100000 | 0x100000 | MUST-MATCH | our load address = kernel's code32_start |
| 0x218 | 4 | ramdisk_image | 0x1f6ea000 | 0x00000000 | LOADER-SPECIFIC | we ship NO initrd (brief: conventional-load only) |
| 0x21c | 4 | ramdisk_size | 0x8d4f07 | 0x00000000 | LOADER-SPECIFIC | no initrd |
| 0x220 | 4 | bootsect_kludge | 0x0 | 0x0 | MUST-MATCH | — |
| 0x224 | 2 | heap_end_ptr | 0xf5f4 | ours = end of our real-mode heap arena (FIXED VALUE at step 2; e.g. 0xefff-class) | LOADER-SPECIFIC | layout of OUR loader's heap; only required valid when loadflags&0x80 |
| 0x226 | 1 | ext_loader_ver | 0x00 | 0x00 | MUST-MATCH | — |
| 0x227 | 1 | ext_loader_type | 0x00 | 0x00 | MUST-MATCH | — |
| 0x228 | 4 | cmd_line_ptr | 0x1f800 | our cmdline buffer address (FIXED at step 2 — choose same 0x1f800 if layout allows) | LIKELY-MATCH | structural, content-checked by L2 |
| 0x22c | 4 | initrd_addr_max | 0x7fffffff | 0x7fffffff | MUST-MATCH | kernel-baked value read from bzImage |
| 0x230 | 4 | kernel_alignment | 0x100000 | 0x100000 | MUST-MATCH | kernel-baked |
| 0x234 | 1 | relocatable | 0x01 | 0x01 | MUST-MATCH | kernel-baked |
| 0x235 | 1 | min_alignment | 0x0d | 0x0d | MUST-MATCH | kernel-baked |
| 0x236 | 2 | xloadflags | 0x0004 | 0x0004 | MUST-MATCH | kernel-baked |
| 0x238 | 4 | cmdline_size | 0x7ff | 0x7ff | MUST-MATCH | kernel-baked |
| 0x23c | 4 | hardware_subarch | 0x0 | 0x0 | MUST-MATCH | kernel-baked |
| 0x240 | 4 | hardware_subarch_data | 0x0 | 0x0 | MUST-MATCH | zero |
| 0x244 | 4 | version_string | 0x0 (not set) | 0x0 | MUST-MATCH | optional, unused |
| 0x248 | 4 | payload_offset | 0x104 | 0x104 | MUST-MATCH | kernel-baked |
| 0x24c | 4 | payload_length | 0x40d69a | 0x40d69a | MUST-MATCH | kernel-baked |
| 0x250 | 4 | setup_data | 0x0 | 0x0 | MUST-MATCH | no setup_data chain |
| 0x254 | 4 | setup_data_hi | 0x0 | 0x0 | MUST-MATCH | — |
| 0x258 | 8 | pref_address | 0x100000 | 0x100000 | MUST-MATCH | kernel-baked |
| 0x260 | 4 | init_size | 0x959000 | 0x959000 | MUST-MATCH | kernel-baked |
| 0x264 | 4 | handover_offset | 0xc0 | 0xc0 | MUST-MATCH | kernel-baked (unused, EFI) |
| 0x1ec–0x1f0 region + e820 table 0x2d0–0x358 | 7×20B | e820_table | 7 entries (see ORACLE_BOOT_PARAMS.md) | same 7 entries | MUST-MATCH | copied from QEMU fw map, byte-identical by construction (same -M pc -m 512) |

**Byte-true note (measured this run from `oracle_zp_leg0.bin`; supersedes
doc prose where they disagree):** the doc's low-field table contains
misparses — it places root_flags at 0x1f6 value 0x0004 (protocol offset is
0x1f2; 0x1f6 is the third byte of syssize, which is why the doc "saw" 0x04),
gives ram_size as 0xfffc0000 (measured 0xffff0000), and calls 0x1fc a
"vid_mode 0xaa44aa00 region" (0x1fc is root_dev=0x0200; vid_mode is 0x1fa,
measured 0xffff = normal). The canonical protocol layout — setup_sects 0x1f1,
root_flags 0x1f2, syssize 0x1f4, ram_size 0x1f8, vid_mode 0x1fa, root_dev
0x1fc, boot_flag 0x1fe — fits the measured bytes exactly. This affects
DOCUMENTATION only: the differ compares bytes at fixed offsets and never
re-derives fields, so the gate is unaffected either way. The oracle dumps
sha-match their pins, so the artifacts are sound; the doc drift is filed as
`.builder_queue/REPAIR_PENDING_bm902_oracle_doc_drift.md` (oracle doc is
must-not-touch per the brief).

## Whitelist contract (machine-consumed summary — the differ reads this)

LOADER-SPECIFIC / STAGE2-CHOICE byte offsets (whitelist for L1):

```
0x000-0x1e7   STAGE2-CHOICE (setup leftovers region: we zero it; diffs named+counted)
0x1f2-0x1f3   root_flags        (LIKELY-MATCH in table, cheap to reproduce — kept white to not couple L1 to a choice)
0x1f8-0x1fb   ram_size leftover
0x1fa-0x1fb   vid_mode          (subset of above range; union arithmetic in gate)
0x1fc-0x1fd   root_dev
0x20c-0x20f   start_sys_seg
0x210         type_of_loader
0x212-0x213   setup_move_size
0x218-0x21f   ramdisk_image + ramdisk_size
0x224-0x225   heap_end_ptr
0x228-0x22b   cmd_line_ptr   (whitelisted ONLY because address may move; content gate is L2)
```

Count assertion: the gate parses the fenced block (ranges INCLUSIVE,
`0xAAA-0xBBB` single offsets or bands), builds the UNION of whitelisted byte
offsets (overlaps merged: 0x1fa-0x1fb ⊂ 0x1f8-0x1fb), adds the 0x000-0x1e7
band, and fails L1 on any diff byte outside that union. Deliberately NOT in
the whitelist: 0x211 loadflags (our value must be correct, not excused),
0x214 code32_start, 0x1fe boot_flag, 0x202 header, and every kernel-baked
field — those are the gate's teeth.

## cmdline classification

Oracle: `loglevel=3 cde console=ttyS0,115200 initrd=/boot/core.gz
BOOT_IMAGE=/boot/vmlinuz` NUL-terminated at byte 83, ptr 0x1f800.
Ours: stage2 places the SAME string (it is the boot recipe we want the
kernel to see; `initrd=` is vestigial without an initrd but byte-equality is
the brief's L2 default and we choose byte-equality over structural-validity —
RECORDED CHOICE per brief: **byte-exact oracle cmdline string, including
`initrd=`, rationale: removes an entire class of whitelist; revisit only if
the kernel's initrd-absent behavior requires it, which BM903 will show, not
BM902**).

## Registers classification

| Reg | Oracle | Ours | Class |
|---|---|---|---|
| rip | 0x100000 | 0x100000 | MUST-MATCH |
| rsi | 0x13ab0 | wherever WE place boot_params (FIXED at step 2; ideally same 0x13ab0 if our memory map allows — decide at step 2, whitelisted if moved) | LIKELY-MATCH |
| cs | 0x10 flat | 0x10 flat | MUST-MATCH |
| ds/ss/es | 0x18 flat | 0x18 flat | MUST-MATCH |
| eflags | 0x46 (IF=0) | 0x46 (cli + popf-equivalent state; IF must be 0, reserved bits 0) | MUST-MATCH (value; ZF/PF incidental — see note) |
| cr0 | 0x11 (PE, PG=0) | 0x11 | MUST-MATCH |
| cr3 | 0x0 | 0x0 | MUST-MATCH |
| cr4 | 0x0 | 0x0 | MUST-MATCH |
| rax | 0x100000 | spec: undefined — set 0x100000 anyway to shrink the diff | MUST-MATCH (chosen) |
| rbx,rcx,rdx,rdi,rbp | 0 | 0 | MUST-MATCH |
| rsp | 0x1f784 | our stack top (whitelisted) | LOADER-SPECIFIC |

Note on eflags bits 1/2/4/6 (bit1 always-1, ZF, PF are incidental CPU flags —
the protocol constrains only IF=0): the REGISTER diff leg compares full values
and the oracle's 0x46 is achievable exactly (`push $0x46; popf` with IF then
cli-equivalent, or cli before the composition); if our composition lands on a
different incidental-bit pattern, 0x00000046 stays the target and any delta
is a NAMED diff in the receipt, not a silent pass.

## Open questions carried to step 2 (none block this plan's commit)

- Q1: exact `type_of_loader` for a self-built stage2 (0xff vs a 0xE0-class
  ID). Protocol allows 0xff; kernel behavior identical. Decide at step 2 when
  the stage2 skeleton exists; the whitelist contains the offset either way.
- Q2: rsi/cmdline addresses — reuse oracle addresses (0x13ab0/0x1f800) if our
  memory map allows; the nearer we hold to the oracle layout, the smaller the
  variability table gets.

## What this plan does NOT decide (honest boundary)

- No stage2 code exists yet; "ours" columns are targets, not measurements.
- The gate's RED legs (L4 flipped byte, L5 mutant table) are defined in the
  brief and will be demonstrated when `run_bm902_diff.sh` exists (step 3).
- The 0x000–0x1e7 STAGE2-CHOICE classification is this plan's one judgment
  call beyond the brief's letter: the oracle's low region is isolinux's
  real-mode leftovers, not protocol-defined handoff state. If Jericho
  disagrees, the cheap reversal is: drop 0x000–0x1e7 from the whitelist,
  stage2 replays screen_info/EDD bytes — a strictly larger stage2. Flagged
  here BEFORE any code, per the "commit the plan before capture" rule.
