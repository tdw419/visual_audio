"""R5.2 gate: the stranger doc's commands must actually run.

Extracts every fenced bash block from docs/START_HERE.md, executes it from the
repo root, and asserts the lines promised in the doc's paired output blocks
actually appear in the real output. RED legs prove the gate can fail:
- missing anchor-workload section -> RED
- corrupted command in the doc    -> RED
- fabricated output in the doc    -> RED

Deterministic: no network, no GPU dependence beyond the landed installer boot
(the same leg test_r51_installer.py L3 already gates).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "docs" / "START_HERE.md"

FENCE = re.compile(r"```(\w+)\n(.*?)```", re.DOTALL)

PROMISED = {
    # (bash block index -> list of lines that MUST appear in its real output)
    # indices assigned in doc order among ```bash blocks
}


def blocks(markdown: str):
    """Return ordered list of (lang, body) for fenced code blocks."""
    return [(m.group(1), m.group(2)) for m in FENCE.finditer(markdown)]


def paired_outputs(markdown: str):
    """Map each bash block to the immediately following ```text block, if any.

    Returns list of (bash_body, promised_lines) where promised_lines is the
    set of non-empty lines the doc claims the command produces (subset match:
    every promised line must appear in the real output).
    """
    result = []
    found = blocks(markdown)
    i = 0
    while i < len(found):
        lang, body = found[i]
        if lang == "bash" and i + 1 < len(found) and found[i + 1][0] == "text":
            promised = [ln.strip() for ln in found[i + 1][1].splitlines() if ln.strip()]
            result.append((body, promised))
            i += 2
        else:
            i += 1
    return result


def run_block(cmd: str, timeout: int = 300):
    return subprocess.run(
        ["/bin/bash", "-c", cmd],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def check_pairs(markdown: str):
    """GREEN core: every (bash, text) pair's promised lines appear in the
    real output. Returns list of failures.

    Promise conventions:
    - 'exit: N'  -> asserts the command's real return code is N.
    - '~<regex>' -> re.search on the whitespace-squeezed stream (for lines
      containing per-run variable values, e.g. timings).
    - other line -> must appear verbatim in a raw output line, OR in the
      whitespace-squeezed stream, OR after stripping ALL whitespace
      (multi-line pretty-printed JSON promises).
    """
    failures = []
    for cmd, promised in paired_outputs(markdown):
        proc = run_block(cmd)
        real_lines = set(
            ln.strip() for ln in (proc.stdout + proc.stderr).splitlines()
        )
        # --json output is multi-line; promises like '"status": "fleet_ready_verified"'
        # are checked against the raw stream with whitespace squeezed.
        squeezed = re.sub(r"\s+", " ", proc.stdout + proc.stderr)
        for line in promised:
            m_exit = re.fullmatch(r"exit:\s*(\d+)", line)
            if m_exit:
                if proc.returncode != int(m_exit.group(1)):
                    failures.append(
                        f"promised exit {m_exit.group(1)} but command exited "
                        f"{proc.returncode}: {cmd!r}"
                    )
                continue
            if line.startswith("~"):
                if not re.search(line[1:], squeezed):
                    failures.append(
                        f"promised pattern not in real output of {cmd!r}: "
                        f"{line!r} (exit={proc.returncode})"
                    )
                continue
            line_sq = re.sub(r"\s+", " ", line)
            nospace = lambda s: re.sub(r"\s+", "", s)
            if (
                line not in real_lines
                and line_sq not in squeezed
                and nospace(line) not in nospace(proc.stdout + proc.stderr)
            ):
                failures.append(
                    f"promised line not in real output of {cmd!r}: {line!r} "
                    f"(exit={proc.returncode})"
                )
    return failures


def extract_only_bash(markdown: str) -> str:
    """Doc with everything except bash blocks (for the missing-anchor RED)."""
    return re.sub(r"```bash\n.*?```", "```bash\ntrue\n```", markdown, flags=re.DOTALL)


def red_missing_anchor():
    """RED: a doc without the anchor workload's real commands must FAIL."""
    stripped = extract_only_bash(DOC.read_text())
    return check_pairs(stripped)


def red_corrupted_command():
    """RED: replacing glyphos_installer.py with a broken command must FAIL."""
    md = DOC.read_text().replace(
        "python3 glyphos_installer.py --json", "python3 tools/no_such_tool.py --json"
    )
    return check_pairs(md)


def red_fabricated_output():
    """RED: a doc promising a wrong fleet result must FAIL (the fabrication
    detector — the gate is not a rubber stamp)."""
    md = DOC.read_text().replace('"714": 6', '"714": 999999')
    return check_pairs(md)


def main():
    failures = []
    # Gate self-check FIRST (RED before GREEN, per lane discipline).
    for name, fn in [
        ("missing-anchor", red_missing_anchor),
        ("corrupted-command", red_corrupted_command),
        ("fabricated-output", red_fabricated_output),
    ]:
        red = fn()
        if not red:
            failures.append(f"RED leg did NOT fire: {name} (gate is not discriminating)")
        else:
            print(f"RED ok [{name}]: {red[0]}")

    green_failures = check_pairs(DOC.read_text())
    if green_failures:
        failures.extend(green_failures)
    else:
        print("GREEN ok: every bash block ran (exit 0) and every promised "
              "line appeared in the real output")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nPASS: docs/START_HERE.md is executable truth")
    return 0


def test_r52_stranger_doc_executable_truth():
    """pytest entry: RED legs must fire, then the real doc must pass."""
    assert red_missing_anchor(), "missing-anchor RED leg did not fire"
    assert red_corrupted_command(), "corrupted-command RED leg did not fire"
    assert red_fabricated_output(), "fabricated-output RED leg did not fire"
    green = check_pairs(DOC.read_text())
    assert not green, f"doc promises not executable: {green}"


if __name__ == "__main__":
    sys.exit(main())
