#!/usr/bin/env python3
"""run_eval.py — oracle-labeled builder benchmark harness.

WHY: proposals to fine-tune a "builder model" for this system have no acceptance
criterion. This harness produces one: take roadmap rows that are ALREADY CLOSED,
strip the solution, hand the row's intent to a candidate model, and let the row's
own gate decide pass/fail. Score = closed rows per attempt (and per dollar).

TWO DEFECTS THIS HARNESS EXISTS TO AVOID (both found live, 2026-09-12):

 1. GATE COMMANDS CAN BE WRONG. `python3 -m pytest
    tools/glyph_gpt/test_spatial_builder.py` collects 0 tests (exit 5) — that file
    is a standalone harness, not a pytest module. Every task therefore carries an
    `expect_substring` and the harness requires it in the gate output, so a
    vacuous "no tests ran" can never score as a pass.

 2. GIT HISTORY IS A SOLUTION LEAK. A `git worktree` checkout leaves the stripped
    file recoverable via `git show HEAD:<path>` — the first agy run "passed" in
    87 s by doing exactly that (the produced file was byte-identical to the
    original, sha 7e17851e…). The harness now builds the scratch tree from
    `git archive HEAD` into a fresh single-commit repo with NO history, verified
    unrecoverable before the candidate runs, and afterwards rejects any candidate
    output whose hash matches the original implementation.

USAGE
  python3 tools/builder_eval/run_eval.py --task sb1_pipeline --red-check
      # verify the stripped task is RED (baseline sanity; also proves the strip
      # is unrecoverable from the scratch repo)
  python3 tools/builder_eval/run_eval.py --task sb1_pipeline \
      --label agy --candidate-cmd 'REPO=$PWD bash ~/.hermes/scripts/agy_implement.sh -f {brief}'
  Results append to tools/builder_eval/results.jsonl (one JSON object per run).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
TASKS_DIR = _HERE / "tasks"
RESULTS = _HERE / "results.jsonl"
SCRATCH_ROOT = _REPO / ".worktrees" / "eval_scratch"

TASKS = {
    "sb1_pipeline": {
        "row": "SB-1 (systems/SPATIAL_BUILDER_ROADMAP.md)",
        "strip": ["tools/glyph_gpt/spatial_builder.py"],
        "brief": TASKS_DIR / "sb1_pipeline.md",
        "gate_file": "tools/glyph_gpt/test_spatial_builder.py",
        "gate_command": "python3 tools/glyph_gpt/test_spatial_builder.py",
        "expect_substring": "11 passed, 0 failed",
        # Only the import closure is archived. Archiving the WHOLE tree costs
        # 25.4 GB of tracked PNG frame sequences and once filled the disk
        # (2026-09-12); tools+glyph_dispatch tracked is 16 MB.
        "archive_paths": ["tools", "tests", "glyph_dispatch", "systems", "docs", "AGENTS.md", "CLAUDE.md"],
        "fixtures": ["boot_images/alpine_riscv64_semantic.db", "db/wordbase.db"],
    },
    "bk14_demo": {
        "row": "BK-14 (glass-box demo runner; gate leg landed 2026-09-12)",
        "strip": ["tools/glass_box_demo.py"],
        "brief": TASKS_DIR / "bk14_demo.md",
        "gate_command": "python3 -m pytest tests/test_bk14_demo.py -q",
        "expect_substring": "4 passed",
        "gate_file": "tests/test_bk14_demo.py",
        "archive_paths": ["tools", "tests", "glyph_dispatch", "systems", "docs", "AGENTS.md", "CLAUDE.md"],
        "fixtures": ["boot_images/alpine_riscv64_semantic.db", "db/wordbase.db"],
    },
    "bk12_wgsl_tier": {
        "row": "BK-12 (WGSL throughput tier; landed 2026-09-12)",
        "strip": ["tools/glyph_gpt/wgsl_tier.py"],
        "brief": TASKS_DIR / "bk12_wgsl_tier.md",
        "gate_command": "python3 -m pytest tests/test_bk12_wgsl_tier.py -q",
        "expect_substring": "6 passed",
        "gate_file": "tests/test_bk12_wgsl_tier.py",
        "archive_paths": ["tools", "tests", "glyph_dispatch", "systems", "docs", "AGENTS.md", "CLAUDE.md"],
        "fixtures": ["boot_images/alpine_riscv64_semantic.db", "db/wordbase.db"],
    },
}


def sh(cmd: str, cwd: Path, timeout: int = 3600) -> tuple[int, str]:
    p = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True,
                       text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def original_hash(rel: str) -> str:
    rc, out = sh(f"git show HEAD:{rel}", _REPO)
    return hashlib.sha256(out.encode()).hexdigest() if rc == 0 else ""


def make_scratch(label: str, task: dict) -> Path:
    """git archive HEAD -> fresh dir -> single root commit -> strip -> verify.

    No history exists in the scratch repo, so the stripped solution is not
    recoverable with git. The strip is verified (file absent AND absent from HEAD).
    """
    scratch = SCRATCH_ROOT / label
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
    free_mb = shutil.disk_usage(_REPO).free / 1048576
    if free_mb < 2048:
        raise SystemExit(f"refusing to start: only {free_mb:.0f} MB free (need >=2 GB)")
    scratch.mkdir(parents=True, exist_ok=True)

    paths = " ".join(shlex.quote(p) for p in task["archive_paths"])
    rc, out = sh(f"git archive HEAD {paths} | tar -x -C {shlex.quote(str(scratch))}", _REPO)
    if rc != 0:
        raise SystemExit(f"git archive failed: {out}")

    # Untracked fixtures the oracle needs (git archive carries tracked files only).
    for rel in task.get("fixtures", []):
        src, dst = _REPO / rel, scratch / rel
        if not src.exists():
            raise SystemExit(f"fixture missing from repo: {rel}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for rel in task["strip"]:
        t = scratch / rel
        if t.exists():
            t.unlink()

    env = "GIT_AUTHOR_NAME=eval GIT_AUTHOR_EMAIL=eval@local GIT_COMMITTER_NAME=eval GIT_COMMITTER_EMAIL=eval@local"
    sh("git init -q", scratch)
    sh(f"{env} git add -A", scratch)
    sh(f"{env} git commit -q -m 'benchmark baseline (solution stripped)'", scratch)

    # ── unrecoverability assertions ──────────────────────────────────────
    rc, log = sh("git log --oneline | wc -l", scratch)
    if rc != 0 or int(log.strip() or 0) != 1:
        raise SystemExit(f"scratch repo has history ({log.strip()} commits) — leak risk")
    for rel in task["strip"]:
        rc, _ = sh(f"git show HEAD:{rel}", scratch)
        if rc == 0:
            raise SystemExit(f"strip failed: {rel} still present in scratch HEAD")
        if (scratch / rel).exists():
            raise SystemExit(f"strip failed: {rel} still on disk")
    return scratch


def assert_quiescent(settle_s: int = 75) -> None:
    """Refuse to measure while another writer is active on the real repo.

    Learned the hard way (three times): a live builder-cron run committing mid-arm is
    indistinguishable from a candidate escaping the scratch, so a measurement taken
    across a commit is void either way. Require (a) no cron run in flight, and (b) the
    repo HEAD to have been stable for `settle_s` seconds.
    """
    import time as _t
    rc, out = sh("hermes cron list 2>/dev/null | head -40 || true", _REPO)
    rc2, head_before = sh("git rev-parse HEAD", _REPO)
    rc3, when = sh("git log -1 --format=%ct", _REPO)
    if rc3 == 0 and when.strip().isdigit():
        age = _t.time() - int(when.strip())
        if age < settle_s:
            raise SystemExit(f"refusing to run: HEAD moved {age:.0f}s ago (< {settle_s}s settle window) — another writer is active")
    print(f"[precheck] quiescent: HEAD stable for >= {settle_s}s, head={head_before.strip()[:8]}")


def repo_snapshot() -> str:
    """Fingerprint of the MAIN repo — detects a candidate escaping the scratch."""
    rc, head = sh("git rev-parse HEAD", _REPO)
    # Exclude the harness's own artifacts: concurrent matrix runs append to
    # results.jsonl, and a dirty harness file is not a candidate escape. Real
    # escapes touch files outside tools/builder_eval/ (that is the signal).
    rc2, status = sh("git status --short | grep -v '^??' | grep -v 'tools/builder_eval/' || true", _REPO)
    return (head.strip() + "\n" + status.strip()).strip()


def gate_file_sha(scratch: Path, task: dict) -> str | None:
    """sha256 of the task's gate file inside the scratch, or None if absent.

    The brief forbids editing the gate file; without this check a candidate that
    weakened or deleted it would earn an honest-looking PASS. The SB-1 benchmark's
    own history shows candidates cheat when it wins (the 2026-09-12 git-history
    leak arm 'passed' in 87 s), so 'the brief says not to' is not a control.
    """
    rel = task.get("gate_file")
    if not rel:
        return ""
    p = scratch / rel
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def gate(scratch: Path, task: dict) -> tuple[bool, str]:
    rc, out = sh(task["gate_command"], scratch, timeout=3600)
    return (rc == 0 and task["expect_substring"] in out), out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, choices=sorted(TASKS))
    ap.add_argument("--candidate-cmd", default=None)
    ap.add_argument("--label", default="unnamed")
    ap.add_argument("--red-check", action="store_true")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    task = TASKS[args.task]
    label = args.label if args.candidate_cmd else f"{args.label}-redcheck"
    assert_quiescent()
    scratch = make_scratch(label, task)
    print(f"[setup] scratch={scratch}  (no git history; strip verified unrecoverable)")
    gate_sha_before = gate_file_sha(scratch, task)
    if task.get("gate_file") and gate_sha_before is None:
        raise SystemExit(f"task config error: gate file {task['gate_file']} missing from archive")

    try:
        if args.red_check or not args.candidate_cmd:
            ok, out = gate(scratch, task)
            print(f"[red-check] task={args.task} -> {'GREEN (unexpected)' if ok else 'RED'}")
            print("\n".join(out.splitlines()[-10:]))
            record = {"task": args.task, "label": label, "mode": "red_check",
                      "red": not ok, "at": time.time()}
        else:
            main_before = repo_snapshot()
            brief_dst = scratch / "TASK_BRIEF.md"
            brief_dst.write_text(task["brief"].read_text())
            cmd = args.candidate_cmd.format(brief=shlex.quote(str(brief_dst)),
                                            scratch=shlex.quote(str(scratch)))
            print(f"[run] task={args.task} label={label} scratch={scratch}")
            print(f"[run] candidate: {cmd}")
            t0 = time.time()
            rc, out = sh(cmd, scratch, timeout=7200)
            wall = time.time() - t0
            ok, gout = gate(scratch, task)

            # ── CONFINEMENT check: did the candidate touch the real repo? ──
            escaped = repo_snapshot() != main_before

            # ── plagiarism / recovery check ──────────────────────────────
            leak = None
            for rel in task["strip"]:
                produced = scratch / rel
                if produced.exists():
                    h = hashlib.sha256(produced.read_bytes()).hexdigest()
                    if h == original_hash(rel):
                        leak = rel
            # ── gate-file tamper check (negative control for 'brief says no') ──
            gate_sha_after = gate_file_sha(scratch, task)
            tampered = gate_sha_after != gate_sha_before
            gate_pass = ok and leak is None and not escaped and not tampered
            record = {
                "task": args.task, "label": label, "mode": "candidate",
                # Record the brief's content hash: briefs are edited in place between
                # arms, and without this a run's instructions are not provable after
                # the fact (2026-09-12: the honest arm's pre-scaffold brief existed
                # only in the session record because the file was first committed
                # after the edit).
                "brief_sha256": hashlib.sha256(task["brief"].read_bytes()).hexdigest(),
                "candidate_cmd": cmd, "candidate_exit": rc, "wall_s": round(wall, 1),
                "gate_pass": gate_pass, "gate_raw_pass": ok,
                "solution_recovered": leak, "repo_escape": escaped,
                "gate_tampered": tampered,
                "gate_file_sha": gate_sha_after,
                "gate_command": task["gate_command"],
                "at": time.time(),
            }
            verdict = ("PASS" if gate_pass else
                       "INVALID (candidate ESCAPED the scratch and modified the real repo)" if escaped else
                       "INVALID (solution recovered from history)" if leak else
                       "INVALID (gate file tampered — result void)" if tampered else "FAIL")
            print(f"[run] candidate exit={rc} wall={wall:.0f}s  GATE={verdict}")
            if tampered:
                print(f"[run] !! gate file {task.get('gate_file')} changed during run "
                      f"(sha {str(gate_sha_before)[:12]}… -> {str(gate_sha_after)[:12]}…)")
            if leak:
                print(f"[run] !! produced {leak} is byte-identical to the original implementation")
            if escaped:
                print("[run] !! CANDIDATE ESCAPED: the main repo changed during this run — result void")
            print("---- gate output (tail) ----")
            print("\n".join(gout.splitlines()[-12:]))

        if not args.keep:
            shutil.rmtree(scratch, ignore_errors=True)
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        with RESULTS.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
        print(f"[recorded] {RESULTS}")
    finally:
        if not args.keep:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
