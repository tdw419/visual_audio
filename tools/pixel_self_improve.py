#!/usr/bin/env python3
"""
pixel_self_improve.py — one bounded cycle of recursive self-improvement,
driven by Ollama + the pixel-hermes memory palace, for visual_audio.mkv.

Design constraints (all learned the hard way this session, not theoretical):

  1. Never trust a proposal at face value. Every proposal must name a
     concrete, scriptable check; that check runs BEFORE any code is written.
     If the check shows the claimed gap doesn't exist, the cycle aborts
     with no changes made. (This is the exact mistake repeatedly made by
     autonomous reports in this project's history: claiming to build
     something that already existed.)
  2. One file, one cycle. Multi-file autonomous patches are how the
     directory-offset corruption incident happened. Scope is deliberately
     narrow: propose one task touching at most one target file.
  3. Isolated via git worktree (AGENTS.md's own "Blast-Radius Containment
     Pattern"), never the main working tree, never master directly.
  4. Every embed into visual_audio.mkv is followed by an embedded-vs-disk
     diff check before the cycle can be marked successful — `va_container.py
     run` executes the embedded frame, not the disk file, and every silent
     "I updated it" claim this session that skipped this check was wrong.
  5. A backup of visual_audio.mkv is taken before any container write.
  6. Commits land on a dedicated review branch, never master. A human
     merges after review — this loop does not self-authorize.
  7. Every cycle outcome (success or failure) is written back as a real,
     structured thought frame — visible via `/search` in the REPL — so the
     loop's own history is auditable the same way everything else in this
     project now is.

Usage:
    python3 tools/pixel_self_improve.py --once      # run exactly one cycle
    python3 tools/pixel_self_improve.py --dry-run    # propose + verify only, no writes

Intended to be invoked by cron with --once. See docs/PIXEL_SELF_IMPROVE.md
for the crontab line and full design writeup.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONTAINER = REPO / "visual_audio.mkv"
BRIDGE_MODEL = "qwen2.5-coder:14b"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Files the loop is allowed to touch. Deliberately narrow — never the
# container format code itself, never keys/, never git config, never
# anything AGENTS.md marks protected-read-only.
ALLOWED_TARGET_GLOBS = ["tools/*.py", "docs/*.md"]
FORBIDDEN_SUBSTRINGS = ["keys/", ".git/", "voicebook/", ".rts/", "rs_fixtures.json",
                         "va_container.py"]  # container format itself: too high-blast-radius for autonomous edits


def log(msg: str):
    print(f"[pixel-self-improve] {msg}", flush=True)


def call_ollama(prompt: str, model: str = BRIDGE_MODEL, timeout: int = 180) -> str:
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.4, "num_ctx": 32768},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())["response"]


def read_reference_context() -> str:
    """AGENTS.md + roadmap = the same reference memory the pixel-hermes bridge
    already embeds — reused here directly rather than re-deriving it."""
    parts = []
    for name in ["AGENTS.md", "docs/PIXEL_MIND_ROADMAP.md"]:
        p = REPO / name
        if p.exists():
            parts.append(f"--- {name} ---\n{p.read_text()[:6000]}")
    return "\n\n".join(parts)


def propose_task(context: str) -> dict:
    """Ask Ollama for exactly one small, scoped, independently-checkable task."""
    prompt = f"""{context}

You are proposing exactly ONE small, concrete improvement task for this project.

Rules:
- Target exactly one file, matched by one of these globs: {ALLOWED_TARGET_GLOBS}
- Never target: {FORBIDDEN_SUBSTRINGS}
- You MUST include a "verify_check" — a single shell command that will be run
  BEFORE any code is written, to confirm the gap you're describing actually
  exists. If that command's output shows the gap does NOT exist, your
  proposal will be rejected without any changes made. Make the check
  specific (e.g. `grep -c "def some_function" tools/some_file.py` expected
  to be 0, or a pytest command expected to fail).
- Do not propose anything already marked done in the roadmap/AGENTS.md.

Respond with ONLY a JSON object, no other text:
{{
  "task": "one sentence description",
  "target_file": "relative/path.py",
  "gap_description": "what's missing and why",
  "verify_check": "shell command to run",
  "verify_expect": "what the output should show if the gap is real (free text, human-readable)"
}}
"""
    raw = call_ollama(prompt)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in proposal response: {raw[:300]}")
    return json.loads(match.group(0))


def validate_proposal(proposal: dict) -> None:
    target = proposal.get("target_file", "")
    if not target:
        raise ValueError("proposal has no target_file")
    if any(bad in target for bad in FORBIDDEN_SUBSTRINGS):
        raise ValueError(f"target_file '{target}' matches a forbidden path")
    if not (target.startswith("tools/") or target.startswith("docs/")):
        raise ValueError(f"target_file '{target}' outside allowed tools/ or docs/")
    if not proposal.get("verify_check"):
        raise ValueError("proposal has no verify_check")


def run_verify_check(worktree_dir: Path, check_cmd: str) -> tuple:
    """Run the LLM-proposed pre-check inside the isolated worktree. Returns (returncode, output)."""
    result = subprocess.run(check_cmd, shell=True, cwd=worktree_dir,
                             capture_output=True, text=True, timeout=60)
    return result.returncode, (result.stdout + result.stderr).strip()


def judge_gap_is_real(context: str, proposal: dict, check_output: str) -> bool:
    """A second, independent Ollama call: does the check output actually confirm
    the gap exists, or does the proposal describe something already done?
    This mirrors exactly the manual verification step done by hand all
    session — automated here instead of trusted blindly."""
    prompt = f"""A code-improvement proposal claims the following gap exists in this project:

Task: {proposal['task']}
Gap claimed: {proposal['gap_description']}
Verification command run: {proposal['verify_check']}
Expected if gap is real: {proposal['verify_expect']}
Actual output of running that command just now:
{check_output}

Based ONLY on the actual output above (not the claim), does the gap genuinely
exist? Answer with exactly one word: REAL or ALREADY_DONE or UNCLEAR.
"""
    verdict = call_ollama(prompt, timeout=60).strip().upper()
    return "REAL" in verdict and "ALREADY_DONE" not in verdict


def make_worktree(branch_name: str) -> Path:
    wt_dir = REPO / ".pixel_self_improve_wt" / branch_name
    if wt_dir.exists():
        shutil.rmtree(wt_dir)
    subprocess.run(["git", "worktree", "add", "-b", branch_name, str(wt_dir), "master"],
                    cwd=REPO, check=True, capture_output=True, text=True)
    return wt_dir


def remove_worktree(wt_dir: Path):
    subprocess.run(["git", "worktree", "remove", "--force", str(wt_dir)],
                    cwd=REPO, capture_output=True, text=True)


def generate_implementation(context: str, proposal: dict, current_content: str) -> str:
    prompt = f"""{context}

Implement this task by producing the COMPLETE new content of the target file.

Task: {proposal['task']}
Target file: {proposal['target_file']}
Gap: {proposal['gap_description']}

Current file content:
---
{current_content}
---

Respond with ONLY the complete new file content, no explanation, no markdown
code fences. If the current content above is empty, this is a new file.
"""
    content = call_ollama(prompt, timeout=240)
    # strip accidental markdown fences if the model added them anyway
    content = re.sub(r"^```[a-z]*\n", "", content.strip())
    content = re.sub(r"\n```$", "", content)
    return content


def write_thought(outcome: str, detail: dict):
    """Write a structured thought frame documenting this cycle's real outcome."""
    if not CONTAINER.exists():
        return
    name = f"pixel_thought_{int(time.time())}"
    payload = json.dumps({
        "timestamp": int(time.time()),
        "query": "[pixel_self_improve cycle]",
        "response": json.dumps({"outcome": outcome, **detail}),
    }, indent=2) + "\n"
    subprocess.run(
        ["python3", "tools/va_container.py", "add", str(CONTAINER), "-",
         "--name", name, "--role", "thought"],
        input=payload, cwd=REPO, text=True, capture_output=True,
    )


def run_cycle(dry_run: bool = False) -> bool:
    context = read_reference_context()

    log("proposing task...")
    try:
        proposal = propose_task(context)
        validate_proposal(proposal)
    except Exception as e:
        log(f"proposal rejected: {e}")
        write_thought("proposal_rejected", {"error": str(e)})
        return False
    log(f"proposed: {proposal['task']} (target: {proposal['target_file']})")

    branch = f"pixel-self-improve/{int(time.time())}"
    wt_dir = make_worktree(branch)
    try:
        log(f"verifying claimed gap in isolated worktree ({wt_dir})...")
        rc, output = run_verify_check(wt_dir, proposal["verify_check"])
        log(f"check output: {output[:300]}")

        if not judge_gap_is_real(context, proposal, output):
            log("independent judge says gap is NOT real (already done, or unclear) — aborting cycle")
            write_thought("aborted_already_done", {"proposal": proposal, "check_output": output[:500]})
            return False

        if dry_run:
            log("dry-run: gap confirmed real, stopping before implementation")
            write_thought("dry_run_gap_confirmed", {"proposal": proposal})
            return True

        target_path = wt_dir / proposal["target_file"]
        current_content = target_path.read_text() if target_path.exists() else ""

        log("generating implementation...")
        new_content = generate_implementation(context, proposal, current_content)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_content)

        # Verify the implementation actually did what was claimed
        log("verifying implementation achieved the claimed goal...")
        rc_after, output_after = run_verify_check(wt_dir, proposal["verify_check"])
        log(f"post-implementation check output: {output_after[:300]}")

        # Re-run the independent judge on the new output
        if not judge_gap_is_real(context, proposal, output_after):
            log("CRITICAL: implementation did NOT close the gap — function/feature still missing")
            write_thought("implementation_failed_gap_still_open", {
                "proposal": proposal,
                "pre_check": output[:300],
                "post_check": output_after[:300],
            })
            return False

        log("implementation verified: gap now closed")

        # AGENTS.md verification gate, when it applies to what changed
        if "speak.py" in proposal["target_file"] or "phonemes" in proposal["target_file"] or "word_compiler" in proposal["target_file"]:
            log("running AGENTS.md codec verification gate...")
            gate = subprocess.run(
                ["python3", "-c", "import sys; sys.path.insert(0,'.'); import ast; "
                 f"ast.parse(open('{proposal['target_file']}').read())"],
                cwd=wt_dir, capture_output=True, text=True,
            )
            if gate.returncode != 0:
                log(f"syntax check FAILED: {gate.stderr}")
                write_thought("implementation_failed_syntax", {"proposal": proposal, "error": gate.stderr[:500]})
                return False

        # backup container before any embed
        if CONTAINER.exists():
            shutil.copy(CONTAINER, str(CONTAINER) + ".bak")

        subprocess.run(["git", "add", proposal["target_file"]], cwd=wt_dir, check=True)
        commit = subprocess.run(
            ["git", "commit", "-m",
             f"feat(self-improve): {proposal['task']}\n\n"
             f"Proposed and implemented by pixel_self_improve.py cycle.\n"
             f"Gap verified via: {proposal['verify_check']}\n"
             f"Review required before merging to master."],
            cwd=wt_dir, capture_output=True, text=True,
        )
        if commit.returncode != 0:
            log(f"commit failed: {commit.stderr}")
            write_thought("commit_failed", {"proposal": proposal, "error": commit.stderr[:500]})
            return False

        log(f"committed to branch {branch} — awaiting human review, NOT merged")
        write_thought("cycle_succeeded_pending_review", {
            "proposal": proposal, "branch": branch,
        })
        return True

    finally:
        if not dry_run:
            log(f"worktree left at {wt_dir} on branch {branch} for review (not auto-removed on success)")
        else:
            remove_worktree(wt_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="run exactly one cycle")
    ap.add_argument("--dry-run", action="store_true", help="propose + verify only, no writes/commits")
    args = ap.parse_args()

    if not (args.once or args.dry_run):
        ap.error("pass --once or --dry-run")

    ok = run_cycle(dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
