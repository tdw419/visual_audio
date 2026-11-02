#!/usr/bin/env python3
"""
Evolution Daemon - trace-diff fitness function for the WGSL RISC-V emulator.

Given a bare-metal payload (an ELF that boots at 0x80000000), this:
  1. Runs the golden QEMU trace and extracts a matching init-state snapshot.
  2. Runs the GPU emulator from that same init state, tracing per-instruction.
  3. Diffs the two traces (ignoring explicitly-listed clock-derived registers).
  4. On divergence, asks Ollama for a WGSL patch, applies it, and re-verifies.
  5. On success or an unparseable/failed patch, stops - never loops forever
     blindly, and never touches git. Rollback is a plain file backup, not a
     git commit - this must never spam commit history on its own.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent.parent
WGSL_PATH = REPO_ROOT / "tools" / "RISCV_CPU_MMU.wgsl"
OLLAMA_API = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:14b"


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=REPO_ROOT)


def extract_init_state(qemu_jsonl: Path, out_path: Path) -> bool:
    with open(qemu_jsonl) as f:
        for line in f:
            e = json.loads(line)
            if e['pc'] >= 0x80000000:
                init_state = {'pc': e['pc'],
                               'regs': {k: v for k, v in e['regs'].items() if not k.startswith('h')}}
                with open(out_path, 'w') as out:
                    json.dump(init_state, out)
                return True
    return False


def run_harness(elf_path: Path, work_dir: Path, max_instructions: int,
                 stall_threshold: int, ignore_regs: list, start_pc: int = 0x80000004):
    """Generate both traces from an existing ELF and diff them."""
    qemu_raw = work_dir / "qemu_raw.log"
    qemu_jsonl = work_dir / "qemu_trace.jsonl"
    init_state = work_dir / "init_state.json"
    gpu_jsonl = work_dir / "gpu_trace.jsonl"

    print(f"[1/4] Running QEMU golden trace for {elf_path.name}...")
    r = run(["python3", "tools/qemu_cpu_trace.py", str(elf_path),
             "--max-instructions", str(max_instructions),
             "--output", str(qemu_raw), "--jsonl", str(qemu_jsonl)],
            timeout=60)
    if r.returncode != 0:
        return False, f"QEMU trace generation failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}"

    print("[2/4] Extracting init state...")
    if not extract_init_state(qemu_jsonl, init_state):
        return False, "Could not find any PC >= 0x80000000 in QEMU trace."

    print("[3/4] Running GPU emulator trace...")
    r = run(["python3", "tools/boot_xv6_gpu.py", str(elf_path),
             "--init-state", str(init_state),
             "--trace", str(gpu_jsonl), "--trace-max", str(max_instructions),
             "--stall-threshold", str(stall_threshold)],
            timeout=120)
    if r.returncode != 0:
        return False, f"GPU emulator run failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}"

    print("[4/4] Diffing traces...")
    cmd = ["python3", "tools/diff_qemu_gpu_traces.py",
           "--qemu-trace", str(qemu_jsonl), "--gpu-trace", str(gpu_jsonl),
           "--start-pc", hex(start_pc), "--max-instructions", str(max_instructions)]
    if ignore_regs:
        cmd.extend(["--ignore-regs", ",".join(ignore_regs)])
    r = run(cmd, timeout=60)

    success = r.returncode == 0 and "all matched" in r.stdout
    return success, r.stdout + "\n" + r.stderr


def ask_ollama(mismatch_log: str, wgsl_source: str, model: str):
    prompt = f"""You are an expert RISC-V and WGSL engineer debugging a GPU-based RISC-V emulator.

The GPU emulator's execution trace diverged from a golden QEMU reference trace.

TRACE MISMATCH LOG (this is diagnostic OUTPUT for you to read - it is NOT
source code, and must never appear in your patch's "find"/"replace" text):
{mismatch_log[-2000:]}

WGSL SOURCE (tools/RISCV_CPU_MMU.wgsl, in full - the actual buggy function
could be anywhere in this file, so search all of it rather than assuming
it's near the top):
{wgsl_source}

CRITICAL INSTRUCTION: You must ONLY patch the WGSL source code shown above.
Do NOT attempt to patch or string-replace the TRACE MISMATCH LOG - it is a
log of what already happened, editing it fixes nothing. Your JSON patch's
"find" string must be an exact substring of the WGSL source, and it must
target the exact logic in the WGSL code that caused the GPU register to
diverge from the QEMU register.

Propose a fix as a JSON array of exact text replacements:
[{{"find": "exact old code from the WGSL SOURCE above", "replace": "exact new code"}}]
Output ONLY the raw JSON array, no markdown fences, no commentary."""

    try:
        resp = requests.post(OLLAMA_API, json={
            "model": model, "prompt": prompt, "stream": False, "format": "json"
        }, timeout=180)
        resp.raise_for_status()
        raw = resp.json()['response']
        print(f"Ollama raw response: {raw[:500]}")
        return json.loads(raw)
    except Exception as e:
        print(f"Ollama request failed: {e}")
        return None


def _coerce_patch_list(patch_data):
    """Ollama's JSON output shape isn't guaranteed - defensively unwrap common
    variants (a bare list, a dict wrapping the list under some key, a single
    edit dict) rather than crash on the first malformed response."""
    if isinstance(patch_data, dict):
        for key in ("patches", "edits", "replacements", "changes"):
            if isinstance(patch_data.get(key), list):
                patch_data = patch_data[key]
                break
        else:
            patch_data = [patch_data]
    if not isinstance(patch_data, list):
        return []
    return [e for e in patch_data if isinstance(e, dict)]


def apply_patch(file_path: Path, patch_data) -> bool:
    edits = _coerce_patch_list(patch_data)
    if not edits:
        print(f"Patch rejected: not a usable edit list (got {type(patch_data).__name__}: {str(patch_data)[:200]!r})")
        return False
    content = file_path.read_text()
    applied = False
    for edit in edits:
        find_str = edit.get('find', '')
        replace_str = edit.get('replace', '')
        if find_str and find_str in content:
            content = content.replace(find_str, replace_str, 1)
            applied = True
        else:
            print(f"Patch entry rejected: could not find {find_str[:80]!r} in source")
    if applied:
        file_path.write_text(content)
    return applied


def evolve(elf_path: Path, max_instructions: int, stall_threshold: int,
           ignore_regs: list, model: str, max_rounds: int, work_dir: Path):
    work_dir.mkdir(parents=True, exist_ok=True)
    backup_path = WGSL_PATH.with_suffix(".wgsl.evolver_backup")

    for round_num in range(1, max_rounds + 1):
        print(f"\n=== Round {round_num}/{max_rounds} ===")
        success, log = run_harness(elf_path, work_dir, max_instructions, stall_threshold, ignore_regs)

        if success:
            print("SUCCESS: traces match within the ignore-list. Evolution complete.")
            if backup_path.exists():
                backup_path.unlink()
            return True

        print(f"--- DIVERGENCE ---\n{log[:1500]}")

        if round_num == max_rounds:
            print("Max rounds reached without convergence. Stopping (no further mutation).")
            break

        wgsl_source = WGSL_PATH.read_text()
        patches = ask_ollama(log, wgsl_source, model)
        if not patches:
            print("Ollama returned no usable patch. Stopping.")
            break

        # Back up BEFORE mutating so a bad patch is trivially reversible -
        # a plain file copy, not a git commit. Never touches git history.
        backup_path.write_text(wgsl_source)
        if apply_patch(WGSL_PATH, patches):
            print("Patch applied, re-verifying next round...")
        else:
            print("Patch could not be applied (no find-string matched). Restoring backup, stopping.")
            WGSL_PATH.write_text(backup_path.read_text())
            break

    return False


def main():
    p = argparse.ArgumentParser(description="Trace-diff-driven evolver for the WGSL RISC-V emulator")
    p.add_argument("elf", type=Path, help="Bare-metal payload ELF to use as the fitness target")
    p.add_argument("--max-instructions", type=int, default=100)
    p.add_argument("--stall-threshold", type=int, default=5000)
    p.add_argument("--ignore-regs", default="x15", help="Comma-separated register list")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--max-rounds", type=int, default=5)
    p.add_argument("--work-dir", type=Path, default=REPO_ROOT / "traces" / "evolver")
    p.add_argument("--check-only", action="store_true",
                    help="Run the harness once and report pass/fail, no Ollama, no mutation")
    args = p.parse_args()

    ignore_regs = [r for r in args.ignore_regs.split(",") if r]
    args.work_dir.mkdir(parents=True, exist_ok=True)

    if args.check_only:
        success, log = run_harness(args.elf, args.work_dir, args.max_instructions,
                                    args.stall_threshold, ignore_regs)
        print("PASS" if success else "FAIL")
        print(log[-1500:])
        sys.exit(0 if success else 1)

    ok = evolve(args.elf, args.max_instructions, args.stall_threshold,
                ignore_regs, args.model, args.max_rounds, args.work_dir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
