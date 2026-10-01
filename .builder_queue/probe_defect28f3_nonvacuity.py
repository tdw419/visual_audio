"""DEFECT-28 file (3) non-vacuity probe (orchestrator's own, out-of-tree).

Builds two NEUTERED copies of the fixed module in a scratch tree beside a copy of the
(byte-identical) gate file and shows that each half of the fix is load-bearing:

  V1  forward `librosa.stft(..., n_fft=eff_n_fft)` re-pinned to `n_fft=self.n_fft`
      -> the three broadcast legs must go RED again.
  V2  per-instance RNG draw reverted to a global `np.random.uniform(...)`
      -> `test_reproduce_with_random_state` must go RED again.

The repo's own `src/griffin_lim.py` is never written to; its sha256 is checked before and
after. Exit 0 only if both variants are RED in the expected legs AND the live file is
byte-identical.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
LIVE = REPO / "src" / "griffin_lim.py"
GATE = REPO / "tests" / "test_griffin_lim.py"
SCRATCH = Path("/tmp/d28f3_probe")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_gate(tag: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_griffin_lim.py", "-q", "--tb=no", "-rf"],
        cwd=SCRATCH,
        capture_output=True,
        text=True,
    )
    tail = "\n".join(proc.stdout.strip().splitlines()[-12:])
    print(f"\n===== {tag} (exit {proc.returncode}) =====\n{tail}")
    return proc.stdout


def build_tree() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    (SCRATCH / "src").mkdir(parents=True)
    (SCRATCH / "tests").mkdir(parents=True)
    shutil.copy(GATE, SCRATCH / "tests" / "test_griffin_lim.py")


def main() -> int:
    before = sha(LIVE)
    original = LIVE.read_text()
    print(f"live src/griffin_lim.py sha256 = {before}")

    failures: list[str] = []

    # --- V1: the n_fft pin is load-bearing -------------------------------------
    v1 = original.replace(
        "reconstructed_spec = librosa.stft(audio, n_fft=eff_n_fft, ",
        "reconstructed_spec = librosa.stft(audio, n_fft=self.n_fft, ",
    )
    if v1 == original:
        failures.append("V1 patch did not apply (pattern not found)")
    else:
        build_tree()
        (SCRATCH / "src" / "griffin_lim.py").write_text(v1)
        out = run_gate("V1: forward stft re-pinned to self.n_fft")
        if "failed" not in out:
            failures.append("V1 was GREEN — the broadcast legs are not guarded by the pin")
        elif "broadcast together" not in out and "ValueError" not in out:
            failures.append("V1 failed for an unexpected reason (no broadcast error)")

    # --- V2: the per-instance RNG is load-bearing ------------------------------
    v2 = original.replace(
        "rng = self._rng if self._rng is not None else np.random\n        phase = rng.uniform(",
        "rng = np.random\n        phase = rng.uniform(",
    )
    if v2 == original:
        failures.append("V2 patch did not apply (pattern not found)")
    else:
        build_tree()
        (SCRATCH / "src" / "griffin_lim.py").write_text(v2)
        out = run_gate("V2: rng draw reverted to global np.random")
        if "test_reproduce_with_random_state" not in out:
            failures.append("V2: test_reproduce_with_random_state stayed green — RNG fix not load-bearing")

    after = sha(LIVE)
    print(f"\nlive src/griffin_lim.py sha256 after = {after}")
    if after != before:
        failures.append("the live module changed during the probe")

    print("\n===== VERDICT =====")
    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    print("PASS: both neuterings go RED in the expected legs; live file byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
