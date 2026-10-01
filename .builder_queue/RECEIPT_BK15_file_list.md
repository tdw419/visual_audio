# RECEIPT — BK-15 SYSCALL_FILE_LIST (0x13), L2-FILES first item

**Landed:** 2026-09-24 ~00:1x CDT · commit `e18312c8` · builder af3e62239ce2
**Authority:** SUPPLY_ROUND8.json L2-FILES ("BK-15 SYSCALL_FILE_LIST (0x13)
lands FIRST") + systems/GLYPH_BACKLOG.md BK-15 row; ledger STATUS ACTIVE at
HEAD a083326a; mailbox check: no RULING_* newer than 2026-09-22 20:38
(all pre-date the last landing).

## What landed

1. **Python engine** (`tools/glyph_isa_v2.py` + sync copy
   `glyph_dispatch/src/glyph/glyph_isa_v2.py`):
   - `_get_fs_allow_roots()` — `GLYPH_FS_ALLOW` colon-separated absolute
     roots, realpaths (the 0x07/0x12 `_get_run_allowlist` model). Unset env
     = empty set = refuse everywhere. Deny-by-default is deliberate:
     enumeration is a more invasive primitive than RUN and must not be
     cheaper to reach.
   - Dispatch branch `0x13`: r1=dir_path_addr, r2=dest_addr, r3=max_bytes.
     realpath(dir) must equal or sit under an allow root (symlinks resolve
     first — a link inside the root pointing outside is refused, gate leg
     L2-symlink). Sorted NUL-separated names into the RAM dest (DEFECT-23-ROOT
     data convention; OOB dest bytes drop, RAM never grows); whole-name
     truncation (a partial name is never emitted). Returns ENTRY COUNT
     (rd), 0 for empty, -1 on refusal/failure. Contract explicitly excludes
     size/mtime (that is L2's `ls -l` upgrade).
2. **WGSL twin** (all 3 copies, triple-sync gate green): `19u` EXCLUDED from
   the `16u..255u` GeOS bridge — `&& syscall_num != 19u`. Pre-fix, the twin
   returned **0** for 0x13: a false listing-success, exactly the
   TICKET_ITEM8 0x12 class. Post-fix it falls to the unknown-syscall path →
   -1. NORMATIVE negative contract (0x07/0x12 precedent): host FS
   enumeration is foreign to the shader threat model.
3. **Spec** (`docs/SYSCALL_ABI_SPEC.md`): `<!--ABI 0x13>` block
   (name/args/storage: RAM/returns/twin: UNIMPLEMENTED/twin_contract:
   NORMATIVE) + containment and reserved-range convention lines updated
   (18u and 19u named as the two bridge exclusions).
4. **Rot guard** (`tests/test_pillar21_abi_spec_rotguard.py`): surface pins
   extended to 0x13 both directions; twin_contract NORMATIVE leg extended
   to five syscalls; bridge-exclusion anchor pins BOTH exclusions;
   mutation probe re-anchored to the 19u exclusion; +4 live L4 legs.

## Gate evidence (rule 4: RED before GREEN)

**RED leg** — engine changes stashed, pre-landing tree:
```
tests/test_bk15_file_list.py
  9 failed, 2 passed in 0.80s
  FAILED: l1 both (lists_files_created_via_file_write, baked_image_end_to_end),
          l2 all three (outside_allow_root, env_unset, symlink_escape),
          l3 missing_dir, l4 twin parity, l5 both
tests/test_pillar21_abi_spec_rotguard.py
  8 failed, 20 passed in 0.11s  (0x13 pins + new L4 legs red pre-landing)
```
Pre-fix behavior demonstrated by the RED: 0x13 hit the Python reserved-range
bridge → returned 0 (success with zero entries — the silent-wrong-answer
class), and the twin returned 0 via its unqualified bridge.

**GREEN leg** — this commit's tree:
```
tests/test_bk15_file_list.py        11 passed in 0.74s
tests/test_pillar21_abi_spec_rotguard.py  28 passed in 0.10s
```

**Live GPU note:** `test_l4_wgsl_twin_returns_neg_one_normative` PASSED (not
skipped) — the wgpu backend was present and the twin's rd == 0xFFFFFFFF was
measured on the actual GPU this session. twin_contract NORMATIVE is
measured, not transcribed.

**Regression family green at e18312c8** (post-landing runs):
pillar23 parity CI + dispatch(SE020) + item-11 grammar + L1 shell
(74 passed) · coverage lint + ram/pixel-space + triple-sync + text console
+ syscall integration (33 passed) · BK-2 + GH-18 + GH-6 + handlers +
ISA v2 (33 passed) · SMODE + glyph-on-glyph + ram/pixel (10 passed).
Pre-commit hooks at commit time: ISA-sync check, 38-test differential suite,
WGSL triple-sync, 8-case parity corpus — all passed.

## What the PASS does NOT prove

- The glyph-sh `files`/`ls` verb is NOT rewired over 0x13 yet — L1's `ls`
  is still the host-side personality shim; that migration is L2 follow-on
  work named in the ledger's NEXT line.
- No `ls -l` columns: size/mtime are outside the 0x13 contract by design.
- No WGSL enumeration capability exists or is claimed; the twin's -1 IS the
  contract. The static reversion pin (L5) guards the bridge exclusion
  between GPU runs; it is source-level, not a behavioral GPU leg.
- Single host, local cgroup; GLYPH_FS_ALLOW semantics tested via
  monkeypatched env on the real handler + one baked-image run.

## Next (per SUPPLY_ROUND8 L2 order)

ls -l columns (FSTAB size/mtime) → `files`/`ls` verb migration over 0x13 →
mkdir/rmdir under allow-scoped root → `>>` append (BK-7). BK-21 after L2
per the round-8 order line.
