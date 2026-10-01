# BRIEF — DEFECT-27: re-author `tests/test_syscall_handlers.py` to the ruled PIXEL-space semantics

**Roadmap row:** SUITE-FIX-1, cluster (3) API/firmware drift (line 355 of `systems/GLYPH_SELF_HOSTING_ROADMAP.md`).
**Step id:** DEFECT-27 (`.builder_queue/DEFECT-27_syscall_handlers_memory_model_drift.json`).

## Spec pointer — READ FIRST (source of truth, not this summary)

1. `.builder_queue/RULING_defect27_store_code_address_space.md` — the ruling is **Option 1**: `SYSCALL_STORE_CODE` (0x11) copies **PIXEL space** (`image`), **engine unchanged**.
2. `.builder_queue/DEFECT-27_syscall_handlers_memory_model_drift.json` — measured state and options.
3. Engine facts (read, do not modify): `tools/glyph_isa_v2.py:1256-1268` (the 0x11 branch: `dest=r1`, `src=r2`, `len=r3`, `_mem_read(image, src+i)` → `_mem_write(image, dest+i, val)`), `:524-538` (`_mem_read`/`_mem_write` on the image), `:706-716` (ST execution: `rs1` = ADDRESS, `rs2` = VALUE), `:300-305` (assembler encoding for the same order), `:1240-1256` (0x10 BOOT_LINUX reads the container signature **from pixel space** via `_mem_read(image, container_addr)` and `+1`).

## Scope (positively bounded)

- **IN SCOPE — the only file you may change:** `tests/test_syscall_handlers.py`.
- **NOT IN SCOPE — must stay byte-identical, prove it with md5 before/after:** `tools/glyph_isa_v2.py` (the ruling forbids touching the engine), `tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL shader, `tests/test_crc_patch.py`, `tests/test_sbi_firmware.py`.
- No new test file. No leg deleted, no leg skipped, no leg `xfail`ed, no assertion weakened or removed.
- Do **NOT** commit. Leave the change in the working tree; the orchestrator re-runs every leg and commits.

## What to change (the ruling's own bullets)

Three measured defects, all in this one file:

1. **Stale `ST` operand order.** The fixtures use `ST <value_reg> <addr_reg>` (e.g. `ST r1 r5` at lines 68, 71, 75, 78, 82, 85, 116, 119; `ST r5 r2` at :151; `ST r5 r1` at :181, :184, :187, :190, :193, :250-262). The live order is `ST <addr_reg> <value_reg>` (`tools/glyph_isa_v2.py:300-305`, execution at `:706-716`). Under the stale order every one of these writes lands at a garbage address, so the program faults/no-ops **before the SYSCALL is ever reached** — which is why the legs pass vacuously today.
2. **`ST` cannot seed pixel space at all, and both syscalls read pixel space.** `ST` writes the 32-bit **RAM** word array (`self.memory`) / the paged store path — never the image. `0x10` reads its container signature from pixels (`_mem_read(image, addr)`) and `0x11` copies pixels. So the fixtures that *intend* to place data where a syscall will read it must seed **host-side, in pixel space**, on the assembled image before `cpu.run(image)`: `cpu._mem_write(image, addr, value)`.
3. **`test_store_code_basic_copy` reads back in the wrong space.** It uses `LD r5 r1` + `PRT r5` (RAM) and asserts `cpu.output[0]`. Under the ruling the readback is pixel space: `cpu._mem_read(image, dest_addr)` — the API `test_store_code_multi_byte:213` already uses.

Required end state, per leg:

- `test_store_code_basic_copy` (@:140): seed the source word with `cpu._mem_write(image, 200, test_value)` after `assemble()` and before `run()`; assert `cpu.registers[4] == 0`; assert the copied value with `cpu._mem_read(image, 100) == test_value`. Drop the `LD`/`PRT`/`cpu.output[0]` readback chain (it reads RAM and is the wrong space) — but you may **not** drop the copy assertion itself.
- `test_store_code_multi_byte` (@:169): seed the five source pixels `0x50..0x54` with `cpu._mem_write(image, ...)`; keep the `_mem_read(image, dest_addr)` readback of all five expected values.
- `test_store_code_overlapping_regions` (@:241) and any other leg that seeds data for a syscall: same treatment (pixel-space `_mem_write` seeding, real `ST` order for any ST that remains).
- `test_boot_linux_valid_vac2_container` (@:43) and `test_boot_linux_cognitive_payload_flag` (@:102): seed the VAC2 header pixels (`0x1000`, `0x1001`; plus the payload/weights words the fixture writes at `0x1004`, `0x1005`, `0x100C`, `0x100D`) with `cpu._mem_write(image, ...)` in the engine's documented byte layout (`tools/glyph_isa_v2.py:1240-1246`: bytes `[p0 & 0xFF, p0>>8, p0>>16, p1 & 0xFF] == b"VAC2"`). These two legs currently assert `registers[6] == 0` **without the syscall ever running**; after this change they must reach the handler and pass for the right reason.
- `test_boot_linux_invalid_signature` (@:22) and `test_store_code_invalid_length` (@:219): make them reach their handlers too; do not change what they assert.

If any leg's assertion turns out to be **unsatisfiable** under the ruled pixel-space semantics, do **not** weaken it and do not delete it — stop, leave the file as-is for that leg, and report the leg, the exact assertion, and the measured actual value.

## Interfaces LOCKED / must-not-touch list

- **Interfaces are LOCKED.** `GlyphCPUv2` / `GlyphAssemblerV2` / `OpcodeMapV2` signatures, the syscall numbering (0x10, 0x11), the `ST` operand order, and the `_mem_read`/`_mem_write` contracts are the spec. If one of them looks wrong, do **not** change it: file `REPAIR_PENDING_defect27_<topic>.md` with 2-4 options cheapest-first, state plainly that it is a skeleton-sign-off change, and report it back.
- **Never weaken a live guard to make a step pass.** If a guard blocks the step, the step is wrong.
- **Must-not-touch:** `tools/glyph_isa_v2.py`, `tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, all WGSL shaders, `tests/test_crc_patch.py`, `tests/test_sbi_firmware.py`, `systems/GLYPH_SELF_HOSTING_ROADMAP.md`, everything under `.builder_queue/` except scratch files you create and name, and `voicebook/` / `.rts/` / `rs_fixtures.json` (AGENTS.md protected assets).

## Gate command (run it yourself, twice, both tails pasted)

```
/usr/bin/python3 -m pytest tests/test_crc_patch.py tests/test_sbi_firmware.py tests/test_syscall_handlers.py -q
```
Expected: **9 passed, 0 failed, rc 0** (RED baseline measured by the orchestrator at `39ad5ce`: `2 failed, 7 passed`, rc 1 — `output/defect27_gate_RED_39ad5ce.txt`).

## Gate clause (concrete, falsifiable)

1. The three failing legs' *current* red forms are gone **by fixing the fixtures, not by relaxing the asserts**: `test_store_code_basic_copy` (was `IndexError` at `:165`) and `test_store_code_multi_byte` (was `Expected 0x0000AA, got 0x000000`) both PASS, and the assertion set is equal-or-stronger than before.
2. **Non-vacuity, required, with evidence pasted:**
   - (a) The `[SYSCALL] STORE_CODE: copied …` / `[SYSCALL] BOOT_LINUX: recognized …` print must now be **present** in each formerly-vacuous leg's stdout (capture it: `contextlib.redirect_stdout`) — today it is absent, which is the measured proof of vacuity.
   - (b) With a **temporary, reverted** edit that disables the 0x11 copy loop, the copy legs must go **RED**. Show that tail, then revert and show `md5sum` of `tools/glyph_isa_v2.py` identical to the pre-probe value (the engine ends byte-identical; if you cannot show that, the probe is not allowed to stand).
   - (c) For a 0x10 leg: seed a **wrong** signature (e.g. `b"XXXX"`) in a scratch probe and show `registers[6] == -1` / the assert going RED — i.e. the container fixture actually reaches the handler. Scratch probe only; the committed file keeps its correct signature.
3. `git status --short` shows **only** `tests/test_syscall_handlers.py` modified (plus any scratch files you name, which you must delete or leave clearly outside the test path).
4. `md5sum tools/glyph_isa_v2.py` before and after is **identical** (paste both).
5. `.venv/bin/python -m pytest tests/test_syscall_handlers.py -q` may be run as an extra leg; if the venv lacks a dependency, say so plainly rather than reporting a green you did not see.

## Failure evidence (RED first — mandatory)

Before editing, run the gate and paste the RED tail (it must be `2 failed, 7 passed`). Do not report success without the pre-edit RED tail and the post-edit GREEN tail, both literal.

## Determinism clause

No network, no Ollama, no GPU, no live model call in any leg you touch or add. If a leg needs one, it does not belong in this step — report it instead.

## Definition of done

`tests/test_syscall_handlers.py` re-authored as above; gate 9/9 rc 0; non-vacuity (a)+(b)+(c) shown with literal tails; engine md5 unchanged; nothing committed; final report names the file, the gate tail, the md5s, and states what the PASS does **not** prove (it does not prove the 0x10 container descriptor is a real VAC2 container on disk, and it does not exercise any syscall outside 0x10/0x11).
