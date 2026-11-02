"""Claude Code audit gate for the Glyph OS builder loop.

Cron: every 30m, no_agent=True — this script IS the job.

Gate logic (cron_system two-tier pattern: cheap check -> expensive worker):
  - HEAD unchanged since last audit  -> exit 0 silently (no Claude call)
  - dirty tree (increment in flight) -> report briefly, do NOT audit WIP
  - new commits (max 3, oldest-first)-> claude -p clean-room audit; print verdict

State: ~/.hermes/state/claude_glyph_audit.json (last_audited_head, history).
Claude runs on this machine, so it can read diffs and run pytest itself.
"""
import json
import os
import subprocess
import sys

REPO = "/home/jericho/projects/zion/projects/visual_audio"
STATE_DIR = os.path.expanduser("~/.hermes/state")
STATE_FILE = os.path.join(STATE_DIR, "claude_glyph_audit.json")
MAX_AUDIT = 3
CLAUDE_TIMEOUT = 600


def git(*args: str) -> str:
    r = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(s: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)


RUNTIME_EXEMPT_DIRS = (
    ".hermes_guest_context/",
    "ubuntu_desktop_pxc1_v3_selfhost/",
)
RUNTIME_EXEMPT_FILES = (
    ".pxc1_delta.jnl",
    ".update_proposals.log",
    ".venv/bin/normalizer",
    ".venv/bin/numba",
    ".builder_queue/decision_log.jsonl",
    "build_map_data.json",
    "build_map.png",
)


def is_exempt(path: str) -> bool:
    return path.startswith(RUNTIME_EXEMPT_DIRS) or path in RUNTIME_EXEMPT_FILES


def main() -> int:
    state = load_state()
    head = git("rev-parse", "HEAD")
    last = state.get("last_audited_head")

    if head == last:
        return 0  # silent tick: nothing new to audit

    status = git("status", "--porcelain")
    dirty_all = [ln for ln in status.splitlines() if not ln.startswith("??")]
    dirty = []
    for ln in dirty_all:
        parts = ln.split(None, 1)
        if len(parts) == 2 and not is_exempt(parts[1]):
            dirty.append(parts[1])

    if dirty:
        print(f"AUDIT DEFERRED: increment in flight ({len(dirty)} dirty tracked files). "
              f"Will audit through {head[:7]} once the tree goes clean.")
        # Do not advance last_audited_head: the clean-tree tick will audit.
        state["last_deferred_head"] = head
        save_state(state)
        return 0

    # Commit range to audit: up to MAX_AUDIT commits after last_audited_head
    rev_range = None
    if last:
        rev_range = f"{last}..{head}"
        verify = subprocess.run(
            ["git", "-C", REPO, "merge-base", "--is-ancestor", last, head],
            capture_output=True,
        )
        if verify.returncode != 0:
            last = None  # history rewritten / branch moved: audit recent only
    if not last:
        rev_range = None

    if rev_range:
        shas = git("log", "--format=%h", "--reverse", rev_range).split()
    else:
        shas = git("log", "--format=%h", "-n", str(MAX_AUDIT)).split()
    shas = shas[-MAX_AUDIT:]
    if not shas:
        state["last_audited_head"] = head
        save_state(state)
        return 0

    log_lines = git(
        "log", "--format=%h %s%n%b---", "-n", str(len(shas)), head
    )
    scope = (
        f"Audit commits {', '.join(shas)} on glyph-transpiler-autoloop in {REPO}.\n"
        f"Commit bodies:\n{log_lines}\n\n"
    )
    prompt = (
        "You are an independent clean-room auditor for the Glyph OS self-hosting loop.\n"
        + scope
        + "For each commit: (1) run the relevant test gate from scratch yourself "
        "(PYTHONPATH=tools:. /usr/bin/python3 -m pytest <gate> -q) — never trust the receipt "
        "in the commit body; (2) diff the change against the receipt and flag any "
        "test weakened post-hoc to pass; (3) check for mechanism-level fakes — does "
        "the test exercise the real mechanism (e.g. USER->SUPER trap, true "
        "round-robin interleaving in step_trace order, box bounds) or a shortcut "
        "that passes while proving nothing; (4) GH-5 invariant: runner.py must stay "
        "<=200 lines with zero dev-time imports.\n"
        "Output format: one line per commit — '<sha> VERDICT: PASS|FAIL|SUSPECT — "
        "<one-sentence evidence>' — then a final line 'OVERALL: <verdict>'. "
        "Be terse. You have shell access; verify, do not speculate."
    )

    try:
        env = dict(os.environ, PYTHONPATH="tools:.", PATH=f"/usr/bin:{os.environ.get('PATH', '')}")
        r = subprocess.run(
            [
                "claude", "-p", prompt,
                "--dangerously-skip-permissions",
                "--allowedTools",
                "Read", "Grep",
                "Bash(git diff:*)", "Bash(git show:*)", "Bash(git log:*)",
                "Bash(python3 -m pytest:*)", "Bash(/usr/bin/python3 -m pytest:*)",
                "Bash(.venv/bin/python3 -m pytest:*)",
            ],
            capture_output=True, text=True, timeout=CLAUDE_TIMEOUT,
            cwd=REPO, env=env,
        )
        verdict = (r.stdout or "").strip() or f"claude stderr: {r.stderr.strip()[:500]}"
    except subprocess.TimeoutExpired:
        verdict = f"AUDIT TIMEOUT: claude did not finish in {CLAUDE_TIMEOUT}s; will retry next tick for same range."

    print(f"AUDIT RANGE: {'..'.join([shas[0], shas[-1]]) if len(shas) > 1 else shas[0]}")
    print(verdict)

    if "AUDIT TIMEOUT" not in verdict:
        state["last_audited_head"] = head
    state["last_verdict"] = {"head": head, "audited": shas, "text": verdict}
    state.setdefault("history", []).append({"head": head, "audited": shas})
    state["history"] = state["history"][-20:]
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
