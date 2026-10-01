# BRIEF — DEFECT-28 file (3): `src/griffin_lim.py` bin-count + `random_state` contract

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:355` (SUITE-FIX-1, cluster (4)).
**Ticket:** `.builder_queue/DEFECT-28_suite_fix1_c4_drift_and_defects.md` § "(3) `test_griffin_lim.py` — investigate the module's bin contract."
**Type:** real module defect (refuted "tolerance" framing long ago). Mechanism-class: restoring the module's own documented behaviour.
**Interfaces are LOCKED** — the public signatures `GriffinLim.__init__ / reconstruct / reconstruct_with_convergence` do not change.
**Definition of done:** `tests/test_griffin_lim.py` 22/22 green with the assertions byte-identical, both non-vacuity
directions shown RED, no neighbour file regressed, and the orchestrator's own re-run (not this claim) is the evidence.
**Never weaken a live guard:** the test assertions and the existing `ValueError`/warning paths stay as they are.
**Do NOT commit.** The orchestrator re-runs the gate and commits.

## Read first (spec pointers)

1. `.builder_queue/DEFECT-28_suite_fix1_c4_drift_and_defects.md` § (3) and the measured table.
2. `src/griffin_lim.py` (232 lines; `git log` shows it is untouched since the initial commit).
3. `tests/test_griffin_lim.py` — **READ ONLY**. It is the consumer contract; every assertion stays byte-identical.
   (It is inside the arc via the row-gate sweep; weakening it is forbidden by the loop's guard rule.)

## Measured RED (orchestrator's own run, HEAD `ba54fb4`)

`/usr/bin/python3 -m pytest tests/test_griffin_lim.py -q` → **4 failed, 18 passed in 0.88 s**,
`output/DEFECT28F3_griffin_RED_prefix.txt` (`src/griffin_lim.py` sha256 `6d3c5921c838948eade05d69e55b3ce6b11184c7f2754d5aad6136c9e114273b`).

**Defect A — two `n_fft` values inside one round trip (3 legs).**
`src/griffin_lim.py:93` and `:141` raise
`ValueError: operands could not be broadcast together with shapes (129,32) (1025,32)` / `(32,16) (129,16)`.
Cause: `librosa.istft(complex_spec, hop_length=self.hop_length)` — the `istft` call passes **no** `n_fft`, so
librosa infers it from the input's bin count (`n_fft = 2*(bins-1)`), while the forward call
`librosa.stft(audio, n_fft=self.n_fft, hop_length=self.hop_length)` uses the constructor's value (default 2048 →
1025 bins). The two directions therefore disagree about the frame geometry and the phase update broadcast-fails.

**Defect B — `random_state` does not reproduce (1 leg).**
`test_reproduce_with_random_state` → `np.testing.assert_array_almost_equal(audio1, audio2)` fails with
99.6 % mismatched elements. `random_state` is honoured only by `np.random.seed(random_state)` in `__init__`
(`:34-35`), but the actual draws happen later inside `reconstruct()` — so constructing `gl2` re-seeds the global
RNG *after* `gl1` has already drawn. The docstring at `:25` documents `random_state: Random seed for reproducibility`.

## The fix (pinned mechanism — measurements decide, not preference)

### (3a) one `n_fft` for the whole round trip, carried by the input

* In **both** `reconstruct` and `reconstruct_with_convergence`, derive the effective frame size from the input:
  `eff_n_fft = 2 * (magnitude_spectrogram.shape[0] - 1)`.
  The spectrogram's bin count is the only carrier of its own frame geometry; a magnitude spectrogram of shape
  `(bins, frames)` is by definition an `n_fft = 2*(bins-1)` spectrogram.
* Pass `n_fft=eff_n_fft` **explicitly** to both `librosa.istft(...)` and `librosa.stft(...)`, so neither direction
  can infer a different value.
* Refuse loudly on an impossible geometry: `bins < 2` → `ValueError` naming the received shape (do not invent a
  fallback, do not silently coerce).
* When `eff_n_fft != self.n_fft`, the **input wins** and a `warnings.warn(...)` names both numbers
  (`self.n_fft`, `eff_n_fft`) — never a silent reinterpretation. (Today the constructor's `n_fft` is the only thing
  that is wrong in every failing leg, so the input value must win; the constructor argument stays in the signature
  and keeps winning whenever it agrees.)
* Do **not** touch `_validate_input`'s existing checks, `_compute_error`, or `estimate_parameters`.

### (3b) `random_state` must actually reproduce

* Give the instance its own generator: in `__init__`, `self._rng = np.random.RandomState(random_state)` when
  `random_state is not None`, else `self._rng = None`; **remove** the `np.random.seed(random_state)` global call
  (it mutates process-global state; that mutation is itself part of the bug) and say so in a comment.
* In both reconstruct paths, draw the initial phase from that generator when it exists, else from global
  `np.random` exactly as today:
  `rng = self._rng if self._rng is not None else np.random; phase = rng.uniform(0, 2*np.pi, size=...)`.
* `random_state=None` behaviour is unchanged (global draws).

Anything else in the file may stay as-is. If you believe a different mechanism is required, STOP and report the
conflict instead of guessing (the orchestrator's second delegation attempt is expensive).

## Scope

* **MAY change:** `src/griffin_lim.py` only.
* **MUST NOT touch:** `tests/test_griffin_lim.py`, any other test file, any other `src/`, `tools/`, `systems/` or
  `.builder_queue/` file. No new files unless strictly required for a probe (use `/tmp` for those).
* **MUST NOT:** `git add`, `git commit`, `git checkout`, `git stash`, or otherwise mutate git state. Leave the tree
  dirty; the orchestrator verifies and commits.

## Gate (the orchestrator re-runs all of these itself — report what you measured)

1. **Gate:** `/usr/bin/python3 -m pytest tests/test_griffin_lim.py -q` → **22 passed, rc=0** (pre-fix: 4 failed / 18 passed).
2. **Non-vacuity, both directions** (use a `/tmp` copy; do not edit tracked files for this):
   * re-pin the forward `stft` `n_fft` back to `self.n_fft` → the three broadcast legs must go RED again;
   * replace the per-instance RNG draw with a global `np.random.uniform` → `test_reproduce_with_random_state` must
     go RED again.
3. **Neighbour gate:** `/usr/bin/python3 -m pytest tests/test_griffin_lim.py tests/test_vcc_validation.py tests/test_cross_modal.py -q`
   → report the counts. `test_cross_modal.py` stays red by design (RULING-PENDING); the **only** permitted change
   versus pre-fix is `test_griffin_lim.py` 4 → 0 failures. Any new failure is a STOP-and-report.
4. **Receipt material:** `sha256sum src/griffin_lim.py` before and after; the exact commands and their raw tails;
   and one paragraph stating what the PASS does **not** prove.

**Interpreter:** `/usr/bin/python3` (py3.12; `librosa` confirmed present). A `.venv` run is informative only.
