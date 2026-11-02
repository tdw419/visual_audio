"""h6 — end-to-end v1: poster -> SAM segments -> glyph decode -> kernel
boots -> serial log. ONE command (hackathon/demo/freeze/E2E.sh), two stages:

  1. decode  — committed poster fixture + recorded SAM-3.1 response through
     the h3/h4 decoder; payload must md5-match the frozen ground truth
     (3292333c9470c37fbf4960b07dbeea79). Pure, offline, deterministic.
  2. boot    — the frozen h1 BOOT_SMOKE gate (bounded Alpine GPU boot,
     banner + SMP). The serial log is preserved as an artifact and the two
     boot milestones are extracted. The full 1.4B-step boot is a MANUAL
     DAY-MARKER: this module never raises BOOT_SMOKE_MAX_STEPS.

Every summary carries wall-time accounting (the receipt budget). Tests never
run the real boot: they inject a stub boot_runner.
"""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import time

DEMO_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parent.parent
FIXTURES = REPO_ROOT / "hackathon" / "tests" / "fixtures"
FREEZE_DIR = DEMO_DIR / "freeze"

# Frozen decode ground truth (h3 fixture set; BOOT_SMOKE freezes the boot side).
GT_PAYLOAD_MD5 = "3292333c9470c37fbf4960b07dbeea79"

# Boot milestones (same greps BOOT_SMOKE.sh gates on).
MILESTONES = {
    "kernel_banner": re.compile(r"(Linux version 6\.12\.31-0-lts.*)"),
    "smp_up": re.compile(r"(smp: Brought up 1 node, 1 CPU)"),
}

BOOT_SMOKE_TIMEOUT_S = 600  # explicit cap under the scheduler kill threshold

# h7 — wall-time budget (h6 receipt): decode <= 5s, boot <= 120s, total 150s.
# A run that blows ANY leg budget reads within_budget False and ok False.
BUDGET_S = {"decode": 5.0, "boot": 120.0, "total": 150.0}

# h7 — the h4 classical fallback is AVAILABLE in the demo chain: the
# committed canonical poster backs the low-confidence route.
DEFAULT_POSTER_PNG = FIXTURES / "glyph_poster_gt.png"
_LOG_PATH_RE = re.compile(r"BOOT_SMOKE PASS: .* \((/tmp/[^)]+\.log)\)")


def decode_stage(response=None, poster_png=None, expected_md5=None):
    """Stage 1: poster -> SAM segments -> glyph decode. Returns
    {"ok", "path", "payload_md5", "payload_len", "gt_md5"}.

    h7 hardening: poster_png defaults to the committed canonical poster so
    the h4 classical fallback is AVAILABLE when the wire score trips the
    confidence gate (previously a low-conf response died with "no poster
    PNG available"); expected_md5 lets a caller pin a non-default ground
    truth (defaults to the frozen canonical md5).
    """
    from hackathon.demo import glyph_decoder

    gt_md5 = expected_md5 if expected_md5 is not None else GT_PAYLOAD_MD5
    if response is None:
        response = json.loads((FIXTURES / "glyph_response_gt.json").read_text())
    if poster_png is None:
        poster_png = DEFAULT_POSTER_PNG.read_bytes()  # decoder contract: bytes
    try:
        result = glyph_decoder.decode_poster_auto(response, poster_png)
    except glyph_decoder.DecodeError as e:
        return {
            "ok": False,
            "path": None,
            "payload_md5": None,
            "payload_len": None,
            "gt_md5": gt_md5,
            "error": str(e),
        }
    except Exception as e:  # h7: the demo stage never tracebacks mid-demo
        return {
            "ok": False,
            "path": None,
            "payload_md5": None,
            "payload_len": None,
            "gt_md5": gt_md5,
            "error": f"{type(e).__name__}: {e}",
        }
    payload = result["payload"]
    md5 = hashlib.md5(payload).hexdigest()
    return {
        "ok": md5 == gt_md5,
        "path": result["path"],
        "payload_md5": md5,
        "payload_len": len(payload),
        "gt_md5": gt_md5,
    }


def _default_boot_runner(cmd, timeout):
    """Run the frozen BOOT_SMOKE gate; preserve its serial log as an artifact.

    Returns (returncode, serial_log_path). The gate itself greps banner + SMP
    and exits nonzero on miss — we re-verify independently from the log.
    """
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )
    match = _LOG_PATH_RE.search(proc.stdout)
    if not match:
        return proc.returncode, None
    return proc.returncode, match.group(1)


def boot_stage(out_dir, boot_runner=None, timeout=BOOT_SMOKE_TIMEOUT_S):
    """Stage 2: kernel boots -> serial log. Returns
    {"ok", "serial_log", "serial_sha256", "serial_bytes", "milestones"}."""
    cmd = ["bash", str(FREEZE_DIR / "BOOT_SMOKE.sh")]
    runner = boot_runner if boot_runner is not None else _default_boot_runner
    rc, src_log = runner(cmd, timeout)

    serial = pathlib.Path(out_dir) / "serial.log"
    milestones: dict = {name: None for name in MILESTONES}
    if src_log is not None and pathlib.Path(src_log).exists():
        shutil.copyfile(src_log, serial)
        text = serial.read_text(errors="replace")
        for name, pattern in MILESTONES.items():
            m = pattern.search(text)
            if m:
                milestones[name] = m.group(1)
    else:
        serial.write_text("")
        text = ""

    ok = rc == 0 and serial.exists() and all(
        v is not None for v in milestones.values()
    )
    return {
        "ok": ok,
        "serial_log": str(serial),
        "serial_sha256": hashlib.sha256(serial.read_bytes()).hexdigest(),
        "serial_bytes": serial.stat().st_size,
        "milestones": milestones,
        "returncode": rc,
    }


def run_e2e(out_dir, boot_runner=None, response=None,
            timeout=BOOT_SMOKE_TIMEOUT_S, budget_s=None):
    """Full pipeline with wall-time accounting. Returns the summary dict.

    h7 hardening: budget_s (default BUDGET_S — the h6 receipt numbers)
    is enforced per run; a leg that exceeds its budget reads within_budget
    False and fails the run even when the leg itself was green.
    """
    budget = dict(BUDGET_S if budget_s is None else budget_s)
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    decode = decode_stage(response=response)
    t1 = time.monotonic()
    boot = boot_stage(out_dir, boot_runner=boot_runner, timeout=timeout)
    t2 = time.monotonic()
    wall_s = {
        "decode": round(t1 - t0, 3),
        "boot": round(t2 - t1, 3),
        "total": round(t2 - t0, 3),
    }
    within_budget = (
        wall_s["decode"] <= budget["decode"]
        and wall_s["boot"] <= budget["boot"]
        and wall_s["total"] <= budget["total"]
    )
    return {
        "ok": decode["ok"] and boot["ok"] and within_budget,
        "decode": decode,
        "boot": boot,
        "wall_s": wall_s,
        "budget_s": budget,
        "within_budget": within_budget,
    }


def main():
    import argparse

    ap = argparse.ArgumentParser(description="h6 end-to-end v1")
    ap.add_argument("--out-dir", required=True,
                    help="directory for the serial.log artifact + summary.json")
    args = ap.parse_args()
    summary = run_e2e(args.out_dir)
    (pathlib.Path(args.out_dir) / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))
    print(
        "E2E %s: decode md5 %s | boot rc %s | serial %s | %.1fs wall"
        % (
            "PASS" if summary["ok"] else "FAIL",
            summary["decode"]["payload_md5"],
            summary["boot"]["returncode"],
            summary["boot"]["serial_log"],
            summary["wall_s"]["total"],
        )
    )
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
