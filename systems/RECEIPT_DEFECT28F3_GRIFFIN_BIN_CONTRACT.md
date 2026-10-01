# RECEIPT — DEFECT-28 file (3): `src/griffin_lim.py` bin contract + `random_state`

**Date:** 2026-09-13 · **Seat:** builder cron `af3e62239ce2` (orchestrator) · **Delegate:** `agy` (exit 0, 120 s,
log `output/agy/agy_impl_20260913_194803.log`) · **Brief:** `.builder_queue/brief_defect28f3_griffin_bin_contract.md`
**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:355` (SUITE-FIX-1, cluster (4)) · **Ticket:**
`.builder_queue/DEFECT-28_suite_fix1_c4_drift_and_defects.md` § (3)
**Class:** mechanism-class (restoring the module's own documented behaviour) → decided by the lane under
`.builder_queue/RULING_standing_authorization.md`; nothing policy-class was touched.

## 1. What was RED, and what the defect actually is

`/usr/bin/python3 -m pytest tests/test_griffin_lim.py -q` at HEAD `ba54fb4` →
**4 failed, 18 passed in 0.88 s** (`output/DEFECT28F3_griffin_RED_prefix.txt`),
module sha256 `6d3c5921c838948eade05d69e55b3ce6b11184c7f2754d5aad6136c9e114273b`.

The ticket's framing ("two call paths in one module disagree about the bin count") is confirmed, and the
measurement splits it into **two independent defects**, neither of them a tolerance:

**Defect A — two `n_fft` values inside one round trip (3 legs).** `src/griffin_lim.py:93` and `:141` raise
`ValueError: operands could not be broadcast together with shapes (129,32) (1025,32)` / `(32,16) (129,16)`.
Cause, measured independently of the module (`/tmp/probe_defect28f3_bin_inference.py`, librosa 0.11.0):
`librosa.istft(complex_spec, hop_length=…)` is called **without** `n_fft`, so librosa infers it from the input's
bin count (bin 129 → `n_fft=256`), while the forward call `librosa.stft(audio, n_fft=self.n_fft, …)` uses the
constructor's 2048 → 1025 bins. The phase-update broadcast then fails. Probes: `istft(bins=129, hop=64)` → 960
samples; `stft(len=960, n_fft=2048)` → 1025 bins (mismatch), `n_fft=256` → 129 bins (match).

**Defect B — `random_state` never reproduced (1 leg).** `test_reproduce_with_random_state` →
`np.testing.assert_array_almost_equal(audio1, audio2)` fails with **99.6 % mismatched elements** (max abs diff
740.8). `random_state` was honoured only by `np.random.seed()` in `__init__`, while the actual draws happen later
inside `reconstruct()` — constructing `gl2` re-seeds the process-global RNG *after* `gl1` has already drawn. The
class docstring at `:25` documents `random_state: Random seed for reproducibility`.

## 2. The fix (delegate `agy`, orchestrator-verified)

`src/griffin_lim.py` only, +45/−9 (`sha256` before `6d3c5921…` → after `b43c3401378c201dd60d72c1d8f8955b5f74d1087ebb82c6a138f3cf333a37ec`):

* **(A)** both reconstruct paths derive `eff_n_fft = 2 * (bins - 1)` from the input spectrogram, pass it
  **explicitly** to both `librosa.istft(...)` and `librosa.stft(...)`, refuse an impossible geometry
  (`bins < 2` → `ValueError` naming the shape), and emit a `UserWarning` naming `self.n_fft` and `eff_n_fft`
  whenever they differ (the input wins; never a silent reinterpretation).
* **(B)** `__init__` builds an instance RNG (`np.random.RandomState(random_state)`), the global `np.random.seed()`
  call is removed, and both reconstruct paths draw the initial phase from that instance RNG when it exists —
  falling back to global `np.random` exactly as before when `random_state is None`.
* Untouched: `_validate_input`, `_compute_error`, `estimate_parameters`, all public signatures, every assertion in
  `tests/test_griffin_lim.py` (sha256 `8ac354222667cbc496682bcc867c542b6b5f1b58455286ebf3bec9f3c961380b`, unchanged).

## 3. Gate legs (all re-run by the orchestrator, never taken from the delegate)

| step | command | result |
|---|---|---|
| **GREEN, gate** | `/usr/bin/python3 -m pytest tests/test_griffin_lim.py -q` | **22 passed, rc=0** in 0.90 s (`output/DEFECT28F3_gate_green.txt`) — RED was `4 failed, 18 passed` |
| **non-vacuity A** | `.builder_queue/probe_defect28f3_nonvacuity.py` V1: forward `stft` re-pinned to `self.n_fft` | **3 failed** (the three broadcast legs) — the pin is load-bearing (`output/DEFECT28F3_nonvacuity_orch.txt`) |
| **non-vacuity B** | same probe, V2: per-instance RNG draw reverted to global `np.random` | **1 failed** — `test_reproduce_with_random_state` only; the RNG fix is load-bearing |
| **live-file integrity** | probe re-hashes the module before/after | `b43c3401…` before == after; probes ran in `/tmp/d28f3_probe`, no tracked file written |
| **neighbour gate** | `/usr/bin/python3 -m pytest tests/test_griffin_lim.py tests/test_vcc_validation.py tests/test_cross_modal.py -q` | **6 failed, 33 passed** — pre-fix 10 failed / 29 passed; the only delta is griffin_lim 4 → 0. `test_cross_modal.py`'s 6 stay red by design (RULING-PENDING), `test_vcc_validation.py` 9/9 green |
| **scope check** | `git status --short` | tracked-modified: `src/griffin_lim.py` only (`.update_proposals.log` was already dirty before the delegate started). No tracked file deleted, no test weakened |

## 4. Row gate (SUITE-FIX-1's own command) and full delta attribution

`PATH=/usr/bin:$PATH suite_sweep.sh -b 12G -w 4 -- /usr/bin/python3 tools/suite_iso_harness.py tests -t 150 -w 4 --sink output/SUITE_DEFECT28F3_SINK.jsonl`
→ **257 files / 1669 collected / PASS 243 · FAIL 7 · TIMEOUT 7** in ~552 s
(`output/SUITE_DEFECT28F3_SINK.jsonl`, log `output/SUITE_DEFECT28F3_SWEEP.txt`);
previous sink `output/SUITE_FIX1_FINAL_SINK.jsonl` was 257 files / 1619 collected / PASS 243 · FAIL 10 · TIMEOUT 4.

File-by-file delta, all six changes accounted for:

| file | old → new | attribution |
|---|---|---|
| `tests/test_griffin_lim.py` | FAIL → **PASS** | this tick's fix |
| `tests/test_vcc_validation.py` | FAIL → **PASS** | previous tick's DEFECT-28 (2) landing, carried in this baseline |
| `tests/test_visual_player_command.py` | FAIL → PASS | the documented contention flake (passes in isolation) |
| `tests/test_spatial_rv32i_cpu.py` | PASS → TIMEOUT (3.2 s → 150.6 s) | **load, not this change** |
| `tests/test_sbi_firmware.py` | PASS → TIMEOUT (7.7 s → 150.8 s) | **load, not this change** |
| `tests/test_rv64i_to_glyph_xv6_nano.py` | PASS → TIMEOUT (55.5 s → 150.1 s) | **load, not this change** |

No file went PASS → FAIL. The three new TIMEOUTs are attributed by isolation re-runs on the same interpreter
(`output/DEFECT28F3_TIMEOUT_isolation_orch.txt`): `tests/test_spatial_rv32i_cpu.py` **19 passed in 39.95 s** and
`tests/test_sbi_firmware.py` + `tests/test_rv64i_to_glyph_xv6_nano.py` **13 passed in 49.02 s**, while the machine
carried a load average of 5.8–9.7. None of the three imports `src/griffin_lim.py` (repo-wide: only
`tests/test_griffin_lim.py`, `spectrogram2wav.py`, `phase2_integration_test.py` mention it), so the fix cannot
reach them. This is the class SUITE-COLLECT-1's side of the fence already names: **the sweep cannot yet tell
"slow under load" from "regressed"**, and `-t 150` sits just above these files' heavy-emulation cost.

## 5. What this PASS does NOT prove

* **No perceptual claim.** It proves geometric self-consistency (STFT/ISTFT agree on one `n_fft` derived from the
  input), loud refusal for impossible geometry, and instance-scoped reproducibility. It says nothing about
  reconstruction quality.
* **`spectrogram2wav.py` was not executed.** Its production path constructs `GriffinLim(n_fft=args.n_fft)` and
  previously crashed for any luminance spectrogram whose bin count disagreed; nothing in the tree runs that CLI
  (no test imports it, no sweep record exists for it), so the *improvement* there is reasoned from the mechanism,
  not measured. Not claimed as fixed.
* **`_compute_error`'s `scipy.signal.resample` shape-patch is still in place** and is now dead for consistent
  geometries. Removing it is a separate judgment; leaving it changes no behaviour.
* **A same-instance `reconstruct()` call sequence still advances the RNG** (so two calls on one seeded instance
  differ, exactly as global draws did). The test's contract — two instances with equal `random_state` → identical
  audio — is what is now met.
* **WGSL/GPU legs: none exist for this module** and none were run.
* **The 3 TIMEOUTs and the remaining FAILs are not this row.** The FAIL set (`cross_modal` RULING-PENDING,
  `glyph_wordbook_lookup` leg 1b BLOCKED-ON-DESIGN, `glyphlang_integration`, `mt2_large_scale`,
  `pixel_os_listener_uart`, `synthesis_equivalence`, `syscall_handlers` DEFECT-27) is unchanged from the previous
  sweep and carries its own tickets.

## 6. Teleop note

**No substrate read this tick.** Per the teleoperation skill's rule 1–2, the geo-obs snapshot is the same
archaeology the previous ticks declined to spend (snapshot ~52 h stale, `tick=0`, machine not stepping), and this
row's verdict is CPU-side (module + tests), so it needs no substrate witness. Staleness stated rather than
silently ignored.
