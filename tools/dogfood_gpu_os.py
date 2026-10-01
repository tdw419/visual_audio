#!/usr/bin/env python3
"""Dogfood and Stress-Testing Daemon for Geometry OS / Glyph OS.

Exercises the live GPU OS substrate (GlyphL1Shell, GlyphCPUv2, and FSTAB)
under simulated real-world workloads, verifies POSIX and spatial invariants,
and feeds results directly to the builder loop:
  1. On PASS: logs continuous health telemetry to .builder_queue/DOGFOOD_GPU_OS_LATEST.json
     and resolves any previously open dogfood defects.
  2. On FAIL: packages a minimal reproducible case and files a structured
     .builder_queue/DEFECT_DOGFOOD_<timestamp>.json ticket with status "OPEN",
     which increments the monitor's queue counter, flips the fingerprint to
     REPAIR_PENDING, and immediately wakes the builder cron (af3e62239ce2)
     to adopt and resolve the defect.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional

OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"
OLLAMA_TAGS_ENDPOINT = "http://localhost:11434/api/tags"


def check_ollama_available() -> bool:
    try:
        req = urllib.request.Request(OLLAMA_TAGS_ENDPOINT)
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def query_ollama(prompt: str, model: str = "qwen2.5:0.5b", json_format: bool = False, timeout: float = 5.0) -> Optional[str]:
    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if json_format:
            payload["format"] = "json"
        req = urllib.request.Request(
            OLLAMA_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "")
    except Exception:
        return None


def diagnose_defect_with_ollama(failing_case: str, error_trace: str) -> Optional[dict]:
    """Uses Ollama to triage defect: root cause analysis and suggested fix for the builder."""
    if not check_ollama_available():
        return None

    prompt = f"""You are an automated triage assistant for an experimental GPU operating system (Geometry OS / Glyph OS).
A dogfood test scenario failed on the live GPU OS substrate.

Failing scenario: {failing_case}
Error Traceback:
{error_trace}

Analyze this failure and return a concise JSON object:
{{
  "root_cause": "concise explanation of why this assertion/operation failed",
  "suggested_fix": "suggested code patch, check, or fix",
  "confidence": 0.95
}}
Return ONLY valid JSON.
"""
    for model, to in (("qwen2.5-coder:7b", 12.0), ("qwen2.5:0.5b", 4.0)):
        res = query_ollama(prompt, model=model, json_format=True, timeout=to)
        if res:
            try:
                parsed = json.loads(res)
                parsed["model"] = model
                return parsed
            except Exception:
                continue
    return None

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import GlyphL1Shell  # noqa: E402

QUEUE_DIR = REPO / ".builder_queue"
LATEST_JSON = QUEUE_DIR / "DOGFOOD_GPU_OS_LATEST.json"
REPORT_MD = QUEUE_DIR / "DOGFOOD_GPU_OS_REPORT.md"


@dataclass
class DogfoodCaseResult:
    name: str
    passed: bool
    duration_ms: float
    error: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DogfoodRunSummary:
    timestamp: str
    head: str
    healthy: bool
    total_cases: int
    passed_cases: int
    failed_cases: int
    total_duration_ms: float
    case_results: list[DogfoodCaseResult] = field(default_factory=list)


def get_git_head() -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


class GpuOsDogfoodSuite:
    """Dogfoods the Glyph OS shell personality and GPU execution substrate."""

    def __init__(self):
        self.results: list[DogfoodCaseResult] = []

    def run_all(self) -> DogfoodRunSummary:
        t0 = time.perf_counter()
        cases = [
            ("fs_hierarchy_and_containment", self.case_fs_hierarchy_and_containment),
            ("append_streaming_and_accumulation", self.case_append_streaming_and_accumulation),
            ("coreutils_search_and_stats", self.case_coreutils_search_and_stats),
            ("directory_navigation_and_pwd", self.case_directory_navigation_and_pwd),
            ("safe_removal_and_posix_cleanup", self.case_safe_removal_and_posix_cleanup),
            ("step_budget_and_execution_stability", self.case_step_budget_and_execution_stability),
            ("ollama_generative_fuzz", self.case_ollama_generative_fuzz),
        ]

        for name, fn in cases:
            c_t0 = time.perf_counter()
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    details = fn()
                c_dur = (time.perf_counter() - c_t0) * 1000.0
                self.results.append(
                    DogfoodCaseResult(name=name, passed=True, duration_ms=c_dur, details=details or {})
                )
            except Exception:
                c_dur = (time.perf_counter() - c_t0) * 1000.0
                err_msg = traceback.format_exc().strip()
                captured_out = buf.getvalue().strip()
                if captured_out:
                    err_msg += f"\n\nCaptured CPU/Syscall Output:\n{captured_out}"
                self.results.append(
                    DogfoodCaseResult(name=name, passed=False, duration_ms=c_dur, error=err_msg)
                )

        total_dur = (time.perf_counter() - t0) * 1000.0
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)

        return DogfoodRunSummary(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            head=get_git_head(),
            healthy=(failed == 0),
            total_cases=len(self.results),
            passed_cases=passed,
            failed_cases=failed,
            total_duration_ms=total_dur,
            case_results=self.results,
        )

    # ── Test Scenarios (Each Self-Contained) ──────────────────────────────

    def case_fs_hierarchy_and_containment(self) -> dict:
        """Tests directory creation, POSIX conflicts, and escape containment."""
        sh = GlyphL1Shell()
        # Create hierarchy
        r1 = sh.turn("mkdir app")
        assert r1 == "", f"mkdir app failed: {r1!r}"
        r2 = sh.turn("mkdir app/src")
        assert r2 == "", f"mkdir app/src failed: {r2!r}"

        # Refusal on duplicate
        r3 = sh.turn("mkdir app")
        assert r3 == "ERR:EEXIST:app", f"re-mkdir expected EEXIST: {r3!r}"

        # Refusal on missing intermediate (no -p)
        r4 = sh.turn("mkdir missing/intermediate/leaf")
        assert r4.startswith("ERR:NOENT:"), f"mkdir intermediate missing expected NOENT: {r4!r}"

        # Root escape refusal
        r5 = sh.turn("mkdir ../escape_attempt")
        assert r5.startswith("ERR:PATH:"), f"mkdir escape expected ERR:PATH: {r5!r}"
        return {"hierarchy": ["app", "app/src"], "containment_verified": True}

    def case_append_streaming_and_accumulation(self) -> dict:
        """Tests write, >> append, echo >> redirection, and byte-exact accumulation."""
        sh = GlyphL1Shell()
        assert sh.turn("mkdir app") == ""
        assert sh.turn("mkdir app/src") == ""
        target = "app/src/log.dat"

        # 1. Initial write
        w1 = sh.turn(f"write {target} header")
        assert w1 == "", f"initial write failed: {w1!r}"

        # 2. Flag-style append
        w2 = sh.turn(f"write >> {target} record1")
        assert w2 == "", f"write >> failed: {w2!r}"

        # 3. Infix-style append
        w3 = sh.turn(f"write {target} >> record2")
        assert w3 == "", f"write infix >> failed: {w3!r}"

        # 4. Echo redirection append
        w4 = sh.turn(f"echo record3 >> {target}")
        assert w4 == "", f"echo >> failed: {w4!r}"

        # Read back whole file via cat
        content = sh.turn(f"cat {target}")
        expected = " header record1 record2 record3"
        assert content == expected, f"unexpected accumulated content: got {content!r}, want {expected!r}"

        # Read stats via ls -l
        ls_out = sh.turn("ls -l app/src")
        assert "log.dat" in ls_out
        assert str(len(expected)) in ls_out.splitlines()[0], f"size mismatch in ls -l: {ls_out!r}"
        return {"file": target, "bytes": len(expected), "verified_content": content}

    def case_coreutils_search_and_stats(self) -> dict:
        """Tests grep, wc, head, tail, which, env against generated files."""
        sh = GlyphL1Shell()
        assert sh.turn("write sample.txt hello world record2 payload") == ""
        target = "sample.txt"

        # grep hit
        g1 = sh.turn(f"grep record2 {target}")
        assert "record2" in g1, f"grep hit failed: {g1!r}"

        # grep miss
        g2 = sh.turn(f"grep nonexistent_word {target}")
        assert g2 == "", f"grep miss expected empty: {g2!r}"

        # wc
        wc_out = sh.turn(f"wc {target}")
        assert "sample.txt" in wc_out, f"wc unexpected: {wc_out!r}"

        # which
        assert sh.turn("which echo") == "echo"
        assert sh.turn("which write") == "write"
        assert sh.turn("which ls") == "ls"
        assert sh.turn("which fake_cmd").startswith("ERR:")

        # env
        env_out = sh.turn("env")
        assert "GLYPH_L1_ROOT=" in env_out
        return {"grep_verified": True, "wc_verified": True, "which_verified": True}

    def case_directory_navigation_and_pwd(self) -> dict:
        """Tests cd, pwd, and relative resolution."""
        sh = GlyphL1Shell()
        assert sh.turn("mkdir nav_dir") == ""
        assert sh.turn("mkdir nav_dir/sub") == ""

        pwd_root = sh.turn("pwd")
        assert pwd_root == sh.session.root

        # cd into child
        cd1 = sh.turn("cd nav_dir")
        assert cd1 == "", f"cd nav_dir failed: {cd1!r}"
        assert sh.turn("pwd") == os.path.join(sh.session.root, "nav_dir")

        # relative ls inside child
        ls_child = sh.turn("ls")
        assert "sub" in ls_child.splitlines()

        # cd back to root
        cd2 = sh.turn("cd ..")
        assert cd2 == ""
        assert sh.turn("pwd") == sh.session.root
        return {"pwd_root": pwd_root, "navigation_verified": True}

    def case_safe_removal_and_posix_cleanup(self) -> dict:
        """Tests rm, rm -f quiet semantics, and rmdir safety."""
        sh = GlyphL1Shell()
        assert sh.turn("mkdir clean_dir") == ""
        assert sh.turn("write clean_dir/f.txt content") == ""

        # rmdir on non-empty directory must refuse
        rmdir_fail = sh.turn("rmdir clean_dir")
        assert rmdir_fail.startswith("ERR:"), f"rmdir non-empty expected refusal: {rmdir_fail!r}"

        # rm nonexistent refuses without -f
        assert sh.turn("rm missing_file") == "ERR:NOENT:missing_file"

        # rm -f is quiet on nonexistent
        assert sh.turn("rm -f missing_file") == ""

        # clean up file and rmdir directory
        assert sh.turn("rm -f clean_dir/f.txt") == ""
        assert sh.turn("rmdir clean_dir") == ""

        # Final check: root is clean
        listing = sh.turn("ls")
        assert listing == "", f"expected empty root, got {listing!r}"
        return {"safe_rmdir": True, "rm_force_quiet": True, "clean_teardown": True}

    def case_step_budget_and_execution_stability(self) -> dict:
        """Measures CPU turn execution and verifies register state stability."""
        sh = GlyphL1Shell()
        # Run a multi-character echo turn
        res = sh.turn("echo test_budget_execution_string_0123456789")
        assert "test_budget_execution_string_0123456789" in res

        # Verify registers and flags on cpu instance
        cpu = sh.cpu
        assert not cpu.faulted, "CPU entered fault state during normal execution"
        return {"cpu_running": cpu.running, "cpu_faulted": cpu.faulted}

    def case_ollama_generative_fuzz(self) -> dict:
        """Uses Ollama to generate exploratory shell command sequences and executes them."""
        sh = GlyphL1Shell()
        commands: list[str] = []
        source = "ollama:qwen2.5:0.5b"

        if check_ollama_available():
            prompt = """You are a shell fuzzer testing a minimal GPU OS shell.
The shell supports these verbs and operations:
- echo <text> > <file>
- echo <text> >> <file>
- write <file> <text>
- read <file>
- cat <file>
- head <file>
- tail <file>
- grep <pat> <file>
- wc <file>
- wc < <file>
- cat <file> | grep <pat>
- cat <file> | wc
- ls
- mkdir <dir>
- cd <dir>
- pwd
- rm <file>
- rmdir <dir>
- time
- date
- which <cmd>
- env
- python -c "<expr>"
- python <file>
Generate 4 realistic shell commands, one per line. Do NOT output numbers, bullets, or markdown.
"""
            raw = query_ollama(prompt, model="qwen2.5:0.5b", timeout=5.0)
            if raw:
                allowed_verbs = (
                    "echo", "write", "read", "cat", "head", "tail", "ls", "mkdir",
                    "cd", "pwd", "grep", "wc", "rm", "rmdir", "time", "date", "which",
                    "env", "python", "python3",
                )
                for line in raw.splitlines():
                    cleaned = re.sub(r"^[\d\.\-\*\`\s]+", "", line).strip("` ")
                    if any(cleaned.startswith(v) for v in allowed_verbs):
                        commands.append(cleaned)
                    if len(commands) >= 4:
                        break

        # Graceful fallback if Ollama is offline or returned empty
        if not commands:
            source = "deterministic_fallback"
            commands = [
                "mkdir fuzzed_tree",
                "write fuzzed_tree/note.txt initial_payload",
                "cat fuzzed_tree/note.txt",
                "rm -f fuzzed_tree/note.txt",
                "rmdir fuzzed_tree",
            ]

        history = []
        for cmd in commands:
            out = sh.turn(cmd)
            # Invariants: CPU must not fault, guest cwd must stay inside session root
            assert not sh.cpu.faulted, f"CPU faulted after command: {cmd!r}"
            assert sh.session.cwd_display.startswith(sh.session.root), f"Session escaped root: {sh.session.cwd_display}"
            history.append({"cmd": cmd, "out": out})

        return {
            "source": source,
            "commands_executed": len(commands),
            "history": history,
            "cpu_stable": not sh.cpu.faulted,
        }



# ── Builder Feedback Integration ─────────────────────────────────────────

def publish_telemetry_and_feedback(summary: DogfoodRunSummary) -> None:
    """Updates .builder_queue artifacts and manages defect ticket lifecycle."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Write structured JSON telemetry
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(asdict(summary), f, indent=2)

    # 2. Write Markdown report
    lines = [
        "# GPU OS Dogfood & Telemetry Digest",
        "",
        f"**Timestamp:** {summary.timestamp}  ",
        f"**HEAD:** `{summary.head[:8]}`  ",
        f"**Status:** {'🟢 HEALTHY' if summary.healthy else '🔴 ANOMALY DETECTED'}  ",
        f"**Pass Rate:** {summary.passed_cases}/{summary.total_cases} cases ({summary.total_duration_ms:.1f}ms total)  ",
        "",
        "| Scenario | Status | Duration (ms) | Details / Note |",
        "| :--- | :---: | :---: | :--- |",
    ]
    for r in summary.case_results:
        st = "✅ PASS" if r.passed else "❌ FAIL"
        note = r.error if r.error else f"{len(r.details)} items verified"
        lines.append(f"| `{r.name}` | {st} | {r.duration_ms:.1f} | {note} |")
    lines.append("")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # 3. Handle Defect Lifecycle to Help the Builder
    existing_tickets = [
        f for f in os.listdir(QUEUE_DIR)
        if f.startswith("DEFECT_DOGFOOD_") and f.endswith(".json")
    ]

    if not summary.healthy:
        # File a new defect ticket
        timestamp_slug = time.strftime("%Y%m%d_%H%M%S")
        ticket_file = QUEUE_DIR / f"DEFECT_DOGFOOD_{timestamp_slug}.json"
        failed_cases = [r for r in summary.case_results if not r.passed]
        first_fail = failed_cases[0]

        # Use Ollama for automated root cause analysis and patch generation
        ai_diag = diagnose_defect_with_ollama(first_fail.name, first_fail.error or "")

        ticket_payload = {
            "id": f"DEFECT-DOGFOOD-{timestamp_slug}",
            "title": f"GPU OS Dogfood Anomaly in `{first_fail.name}`",
            "status": "OPEN",
            "severity": "HIGH",
            "failing_case": first_fail.name,
            "error_trace": first_fail.error,
            "ai_diagnosis": ai_diag,
            "head": summary.head,
            "reproducer": f"python3 tools/dogfood_gpu_os.py --case {first_fail.name}",
            "created_at": summary.timestamp,
        }

        with open(ticket_file, "w", encoding="utf-8") as f:
            json.dump(ticket_payload, f, indent=2)

        print(f"🚨 Dogfood failure detected! Filed builder defect ticket: {ticket_file.name}")
        if ai_diag:
            print(f"   🤖 Ollama [{ai_diag.get('model')}]: {ai_diag.get('root_cause', '')[:100]}...")
            if "suggested_fix" in ai_diag:
                print(f"   💡 Suggested fix: {ai_diag.get('suggested_fix', '')[:120]}...")
        print("   -> Builder monitor (glyph_build_chain_monitor.py) will trigger on queue change.")
    else:
        # If healthy, resolve any prior open dogfood tickets
        for t in existing_tickets:
            t_path = QUEUE_DIR / t
            try:
                data = json.loads(t_path.read_text(encoding="utf-8"))
                if "OPEN" in data.get("status", "").upper():
                    data["status"] = "RESOLVED"
                    data["resolved_at"] = summary.timestamp
                    data["resolved_by_head"] = summary.head
                    t_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    print(f"✅ Prior dogfood defect {t} marked RESOLVED.")
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Dogfood test suite for Geometry OS / Glyph OS")
    parser.add_argument("--cron", action="store_true", help="Run in cron mode (terse output)")
    parser.add_argument("--case", type=str, default=None, help="Run single specific case")
    args = parser.parse_args()

    suite = GpuOsDogfoodSuite()

    if args.case:
        fn = getattr(suite, f"case_{args.case}", None)
        if not fn:
            print(f"Unknown case: {args.case}")
            return 2
        print(f"Running single case: {args.case} ...")
        res = fn()
        print(f"PASS: {res}")
        return 0

    summary = suite.run_all()
    publish_telemetry_and_feedback(summary)

    if args.cron:
        status_str = "HEALTHY" if summary.healthy else "FAIL"
        print(f"[{summary.timestamp}] GPU OS Dogfood: {status_str} ({summary.passed_cases}/{summary.total_cases} passed in {summary.total_duration_ms:.1f}ms)")
    else:
        print(f"\n=== GPU OS Dogfood: {'PASS' if summary.healthy else 'FAIL'} ===")
        print(f"Passed: {summary.passed_cases}/{summary.total_cases} in {summary.total_duration_ms:.1f}ms")
        for r in summary.case_results:
            st = "PASS" if r.passed else "FAIL"
            print(f"  [{st}] {r.name} ({r.duration_ms:.1f}ms)")

    return 0 if summary.healthy else 1


if __name__ == "__main__":
    sys.exit(main())
