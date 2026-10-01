# DEFECT-28 — SUITE-FIX-1 cluster (4) is not a tolerance cluster: it is drift + two real defects

**Filed:** 2026-09-13 by builder cron `af3e62239ce2`, HEAD `1f49a92` (`fd9b4e0` + the RUN repair).
**Status:** OPEN — eligible supply for the builder, but **ordered after** the mechanical item below: each file needs a
judgement about *which side is wrong* (module vs test), so pick them one at a time, cheapest first.
**Provenance:** the roadmap row's own text (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:355`, cluster (4)): *"Tolerances/live
services … the tolerance cases may be legitimate expected behaviour and need a decision, not a patch."* **Refuted by
measurement** this tick — none of the three files fails on a tolerance.

## Measured evidence (orchestrator's own run, `output/suite_fix1_c4_tolerance_measure.txt`)

Command: `/usr/bin/python3 -m pytest tests/test_griffin_lim.py tests/test_vcc_validation.py tests/test_cross_modal.py -q --tb=line`
→ **13 failed, 26 passed in 1.43 s**

| file | collected/failed | literal failure | class |
|---|---|---|---|
| `tests/test_cross_modal.py` | 8 / 6 | `AttributeError: module 'cross_modal' has no attribute 'extract_tiles'` at `:86,:103,:138`; `AssertionError: CLI failed: usage: cross_modal.py [-h] {from-image,from-audio,from-text} …` at `:165` | **API drift** (cluster (3) class) |
| `tests/test_griffin_lim.py` | 22 / 4 | `ValueError: operands could not be broadcast together with shapes (32,16) (129,16)` at `src/griffin_lim.py:141`; `(129,32) (1025,32)` and `(257,50) (1025,50)` at `src/griffin_lim.py:93` | **real shape/contract defect** in the module (bin count disagrees: 129/257 vs 1025) |
| `tests/test_vcc_validation.py` | 9 / 3 | `ValueError: Decoded byte out of range at pixel 1 (1,0): 197621`; `… pixel 0 (0,0): 6711656` | **real range violation** in the decode path, or a fixture whose geometry no longer matches the encoder |

The three failing vcc legs are `TestVCCEncodingDecoding::test_large_payload`,
`TestVCCHilbertMapping::test_hilbert_round_trip_consistency`, `TestVCCFixtureManagement::test_fixtures_workflow`.
The four failing griffin_lim legs are `test_reconstruct_with_convergence_quick_convergence`,
`test_reproduce_with_random_state`, `test_different_iteration_counts`, `test_griffin_lim_integration`.

## Cheapest first

> **2026-09-13 tick (HEAD `d3e6513`): file (1) is now MEASURED and the "mechanical drift" classification is
> REFUTED — see `.builder_queue/REPAIR_PENDING_defect28_cross_modal_api.md`.** `tests/test_cross_modal.py` is
> untracked (`.gitignore:101`), dated 2026-07-27, and asserts a `cross_modal` tile API (`extract_tiles`,
> `text_to_tiles`, `tiles_to_audio_byteperfect`) that exists in **no committed revision** — `extract_tiles` in
> history is `extract_tiles_from_frame` in `tools/pixel_dedup_optimized.py:45`; `tiles_to_audio_byteperfect` has
> zero hits. Only the CLI leg is genuine drift (`--output/--audio-output` vs the live `--output-dir`; the other two
> CLI legs already pass, which is the 2/8). The 8/8 gate cannot be met without inventing a tile ABI → held as a
> **design question (RULING-PENDING)**, not worked. Files (2) and (3) are NOT re-measured; still open.

> **2026-09-13 tick (HEAD `6ede59a`): file (2) is MEASURED and LANDED — see
> `.builder_queue/REPAIR_PENDING_defect28c_container_format_authority.md` and
> `systems/RECEIPT_DEFECT28C_VCC_ENCODER.md`.** The binary question the section below poses ("encoder byte-range
> contract, or fixture geometry?") is **neither**: the decoder is CORRECT — it reproduces both pinned
> `vcc_fixtures.json` hashes byte-exact (`systems/glyph_os/tile_demo.rts.png` 16 B, `window_coordinator.rts.png`
> 174 B; `.builder_queue/probe_defect28c_fixture_oracle.py`), and the 3-byte/pixel reading matches neither. The real
> defect was that the tree had **no VCC-format encoder**: `tools/pixelrts_v2_converter.py` has packed 3 bytes/pixel
> since `7e03abb` (a deliberate PXC1-boot variant) and was never the VCC encoder. Fixed additively —
> `tools/vcc_validate.py::encode_rts_png` (byte-exact inverse of its own decoder) with the three round-trip legs
> encoding through it; `decode_rts_png`, `SPECIAL_OFFSET` and the CLI untouched; gate `3 failed/6 passed → 9 passed`,
> non-vacuity RED proven. **Files (1) and (3) remain open; (1) is RULING-PENDING, (3) is untouched.**

> **2026-09-13 tick (HEAD `ba54fb4`): file (3) is MEASURED and LANDED — see
> `.builder_queue/brief_defect28f3_griffin_bin_contract.md` and
> `systems/RECEIPT_DEFECT28F3_GRIFFIN_BIN_CONTRACT.md`.** The section below frames it as "the module's bin
> contract", and that is confirmed — but it is **two** independent defects, not one:
> **(A)** `librosa.istft(...)` was called *without* `n_fft`, so librosa inferred `2*(bins-1)` from the input
> (`istft(bins=129, hop=64)` → 960 samples) while the forward `librosa.stft(audio, n_fft=self.n_fft)` used the
> constructor's 2048 → 1025 bins; the phase update at `src/griffin_lim.py:93,:141` then broadcast-fails (3 legs).
> **(B)** `random_state` was honoured only by `np.random.seed()` in `__init__`, while the draws happen inside
> `reconstruct()` — two instances seeded 42 produced **99.6 %-different** audio, against the docstring at `:25`
> ("Random seed for reproducibility") (1 leg). Fix is module-side only (+45/−9): both paths derive
> `eff_n_fft = 2*(bins-1)` from the input, pass it explicitly to `istft`/`stft`, refuse `bins < 2` loudly and
> `UserWarning`-name any disagreement with `self.n_fft` (input wins); `__init__` builds an instance
> `np.random.RandomState` (the global seed call is removed) and the phase draw uses it, falling back to global
> draws for `random_state=None`. No assertion changed (`tests/test_griffin_lim.py` sha `8ac35422…` before == after).
> Gate `22 passed` (was `4 failed / 18 passed`); non-vacuity both directions (re-pin the forward `stft` → 3 failed;
> revert the RNG → 1 failed); row-gate sweep `PASS 243 · FAIL 7 · TIMEOUT 7` with the full delta attributed —
> **no PASS→FAIL**, and the 3 new TIMEOUTs are load-contention class (all three pass in isolation, none imports the
> changed module). **Files (1) and (3) are therefore resolved as far as this ticket orders them: (2) landed,
> (3) landed, (1) remains RULING-PENDING.**
**(1) `test_cross_modal.py` — mechanical drift, do this one first.** Identify what replaced `extract_tiles` in the
`cross_modal` module and which CLI subcommand(s) `:165` should invoke (`--help` output already names the live set:
`{from-image,from-audio,from-text}`). Fix on the consumer side exactly as the ollama drift was fixed (module is the
product unless measurement says otherwise), preserving every assertion. Gate: `pytest tests/test_cross_modal.py -q` →
**8 passed**, RED-first `6 failed`, non-vacuity by neutering one real behaviour (e.g. the tile extractor's return).

**(2) `test_vcc_validation.py` — investigate, then decide.** Determine whether the encoder's byte range contract or the
fixture geometry drifted (the values 197621 / 6711656 are far outside a byte). Do **not** relax the `ValueError` — it is
the gate that caught this. If the deciding fact is the VCC spec, this becomes a ruling request, not a patch.

**(3) `test_griffin_lim.py` — investigate the module's bin contract.** `(129,16) (1025,16)` / `(257,50) (1025,50)` at
`src/griffin_lim.py:93,141` means two call paths in one module disagree about the bin count; fix the module (not the
assertions) or show the caller is wrong. This is the only one of the three that touches `src/`, so it needs its own
gate showing the broadcast error is gone and the reconstruction quality legs still pass.

## Not in this ticket

**Also observed this tick, not yet its own defect:** `tests/test_visual_player_command.py` went PASS→FAIL in the `-w 4`
row-gate sweep (`output/SUITE_FIX1_FINAL_SINK.jsonl`: 5.94 s, recorded last line is a `ResourceWarning`, not the
assertion) while passing **4/4 in isolation** at the same HEAD (3.15/3.15/3.17 s) and having passed in the previous sweep
~40 min earlier — contention-sensitive, the same class as the documented `test_pixel_lm_train.py` (FAIL 5/6 at `-w 4`,
PASS 6/6 at `-w 1`). Not attributed to this tick's change (only two unrelated test files were modified); it also confirms
the sweep cannot yet tell "flaky under load" from "regressed", which is `SUITE-COLLECT-1`'s side of the fence.

The 4 TIMEOUT files (`test_ollama_security_analysis.py`, `test_pixel_lm_train.py`, `test_probe_stval.py`,
`test_xv6_boot_regression.py`) are the **budget/collect-hang** side — that is `SUITE-COLLECT-1`, still queued.
`tests/test_glyph_wordbook_lookup.py` (0/2) is leg 1b, BLOCKED-ON-DESIGN
(`.builder_queue/REPAIR_PENDING_suite_fix1_wordbook_db_drift.md`). `tests/test_syscall_handlers.py`'s 2 remaining legs
are DEFECT-27, seated with the lane (ABI-semantics ruling).
