#!/usr/bin/env python3
"""tools/syscall_corpus/capture.py — build syscall ground-truth corpus records.

Two capture legs, one JSONL record schema ({"pc"-free, syscall-level}):

  rv64   — compile fixtures/*.c with riscv64-unknown-elf-gcc (-nostdlib, raw
           ecall ABI), run under qemu-riscv64-static -strace, parse QEMU's
           strace dialect. ISA-correct: feeds RV64 glyph/lockstep layers.
  guest  — run a command inside the x86_64 v3_selfhost guest (ssh :2222) under
           stock strace, fetch the raw trace + rc. Semantic ground truth: what
           real programs actually do (ordering, flags, error paths) for the
           POSIX-shim layer (test_gh21_posix_shim, test_gh23_libc_runtime).

Usage:
  capture.py rv64 fixtures/hello_write_exit.c [--out corpus/rv64_syscalls.jsonl]
  capture.py rv64 --all
  capture.py guest "ls -la /var/tmp" [--name ls_tmp] [--out corpus/guest_syscalls.jsonl]

Records are appended (never overwrite) so the corpus grows monotonically;
dedupe/compare is the consumer's job. Raw traces are archived under corpus/raw/.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
CORPUS = HERE / "corpus"
RAW = CORPUS / "raw"

HOST_SSH = ["sshpass", "-p", "israel", "ssh", "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=8", "-p", "2222", "jericho@127.0.0.1"]
GUEST_WORKDIR = "/var/tmp/syscall_corpus"

GCC = "riscv64-unknown-elf-gcc"
GCC_FLAGS = ["-march=rv64imafdc", "-mabi=lp64d", "-nostdlib", "-static", "-O1"]
QEMU = "qemu-riscv64-static"


def _append_record(out_path: Path, record: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def _archive_raw(name: str, kind: str, text: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    p = RAW / f"{name}.{kind}.txt"
    p.write_text(text)
    return p


# ---------------------------------------------------------------------------
# QEMU user-mode -strace dialect
#
#   3993839 openat(AT_FDCWD,"corpus_file.bin",O_WRONLY|O_CREAT|O_TRUNC,0644) = 3
#   3993839 write(1,0xab2a9c40,12)hello glyph
#    = 12                       <- continuation line (payload was inline)
#   3993839 exit_group(0)      <- no ret (final)
#   3992908 exit(7)
#   3993839 brk(NULL) = 0x0000000000011000
# ---------------------------------------------------------------------------
_QEMU_LINE = re.compile(r"^\d+\s+(\w+)\((.*)\)(.*)$")
_QEMU_CONT = re.compile(r"^\s*=\s*(-?\d+)")
_QEMU_RET = re.compile(r"\s*=\s*(-?(?:0x[0-9A-Fa-f]+|\d+))(?:\s*\(.*\))?\s*$")


def _ret_field(token: str) -> tuple[int, int | None, str | None]:
    """Return (sort_key, ret, ret_hex): decimal -> ret, hex -> ret_hex."""
    if token.lower().startswith(("0x", "-0x")):
        return int(token, 16), None, token
    return int(token), int(token), None


def parse_qemu_strace(text: str) -> list[dict]:
    syscalls: list[dict] = []
    pending: dict | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        m = _QEMU_CONT.match(raw_line)
        if m and pending is not None:
            pending["ret"] = int(m.group(1))
            syscalls.append(pending)
            pending = None
            continue
        m = _QEMU_LINE.match(raw_line)
        if not m:
            # unknown noise (e.g. binary output); keep as stderr note
            if pending is not None:
                pending.setdefault("payload", "")
                pending["payload"] += raw_line
            continue
        if pending is not None:  # previous syscall had no ret (exit etc.)
            syscalls.append(pending)
            pending = None
        name, args, tail = m.group(1), m.group(2), m.group(3)
        rec: dict = {"name": name, "args_raw": args.strip()}
        rm = _QEMU_RET.search(tail)
        if rm:
            _, ret, ret_hex = _ret_field(rm.group(1))
            if ret is not None:
                rec["ret"] = ret
            else:
                rec["ret_hex"] = ret_hex
            inline = tail[: rm.start()].strip()
        else:
            inline = tail.strip()
        if inline:
            rec["payload"] = inline
        if "ret" in rec:
            syscalls.append(rec)
        else:
            pending = rec  # ret arrives on a continuation line
    if pending is not None:
        syscalls.append(pending)
    return syscalls


# ---------------------------------------------------------------------------
# Linux strace dialect (guest leg)
#
#   openat(AT_FDCWD, "f", O_WRONLY|O_CREAT|O_TRUNC, 0644) = 3
#   write(1, "hello\n", 6) = 6
#   exit_group(0)     = ?
#   +++ exited with 0 +++
# ---------------------------------------------------------------------------
_STRACE_LINE = re.compile(
    r"^(?:\d+\s+)?(\w+)\((.*)\)\s*=\s*(-?\d+|-?0x[0-9A-Fa-f]+|\?)(?:\s+(\w+).*)?$")


def parse_linux_strace(text: str) -> tuple[list[dict], int | None]:
    syscalls: list[dict] = []
    exited_rc = None
    resumed = re.compile(r"^(?:\d+\s+)?<\.\.\.\s*(\w+)\s+resumed>(.*)$")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("+++"):
            continue
        # "<... vfork resumed>) = 2867" -> "vfork() = 2867" (rest incl. ') = ret')
        m2 = resumed.match(line)
        if m2:
            line = f"{m2.group(1)}({m2.group(2)}"
        m = _STRACE_LINE.match(line)
        if not m:
            continue
        name, args, ret, err = m.group(1), m.group(2), m.group(3), m.group(4)
        rec: dict = {"name": name, "args_raw": " ".join(args.split())}
        if ret != "?":
            if ret.lower().startswith(("-0x", "0x")):
                rec["ret_hex"] = ret
            else:
                rec["ret"] = int(ret)
            if err:
                rec["errno"] = err
        syscalls.append(rec)
    return syscalls, exited_rc


def capture_rv64(fixture: Path, out: Path) -> dict:
    if not fixture.exists():
        raise SystemExit(f"fixture not found: {fixture}")
    name = fixture.stem
    build = CORPUS / "build"
    build.mkdir(parents=True, exist_ok=True)
    binary = build / name

    cc = subprocess.run(
        [GCC, *GCC_FLAGS, "-o", str(binary), str(fixture)],
        capture_output=True, text=True)
    if cc.returncode != 0:
        raise SystemExit(f"build failed:\n{cc.stderr}")
    if cc.stderr.strip():
        print(f"[warn] gcc stderr: {cc.stderr.strip()[:400]}", file=sys.stderr)

    run = subprocess.run([QEMU, "-strace", str(binary)],
                         capture_output=True, text=True, timeout=60, cwd=str(build))
    trace_text = run.stderr

    qemu_ver = subprocess.run([QEMU, "--version"], capture_output=True, text=True
                              ).stdout.splitlines()[0]

    record = {
        "fixture": name,
        "arch": "rv64",
        "source": "qemu-user-strace",
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "toolchain": {"cc": GCC, "flags": GCC_FLAGS, "qemu": qemu_ver},
        "rc": run.returncode,
        "stdout": run.stdout,
        "syscalls": parse_qemu_strace(trace_text),
    }
    raw = _archive_raw(name, "qemu-strace", trace_text)
    _append_record(out, record)
    return {"record": record, "raw": str(raw)}


def capture_guest(command: str, name: str, out: Path) -> dict:
    ssh = HOST_SSH
    pre = (f"mkdir -p {GUEST_WORKDIR} && cd {GUEST_WORKDIR} && "
           f"strace -f -s 256 -o {GUEST_WORKDIR}/{name}.strace "
           f"sh -c { _q(command) }; echo RC=$?")
    proc = subprocess.run([*ssh, pre], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise SystemExit(f"guest ssh failed:\n{proc.stderr}")
    rc_line = next((l for l in proc.stdout.splitlines() if l.startswith("RC=")), "RC=?")
    guest_rc = int(rc_line[3:]) if rc_line[3:].isdigit() else None

    fetch = subprocess.run(
        [*ssh, f"cat {GUEST_WORKDIR}/{name}.strace"],
        capture_output=True, text=True, timeout=60)
    if fetch.returncode != 0:
        raise SystemExit(f"trace fetch failed:\n{fetch.stderr}")
    trace_text = fetch.stdout

    syscalls, _ = parse_linux_strace(trace_text)
    record = {
        "fixture": name,
        "arch": "x86_64",
        "source": "linux-strace",
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "command": command,
        "rc": guest_rc,
        "stdout_tail": proc.stdout.splitlines()[-5:],
        "syscalls": syscalls,
    }
    raw = _archive_raw(name, "linux-strace", trace_text)
    _append_record(out, record)
    return {"record": record, "raw": str(raw)}


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    rv = sub.add_parser("rv64", help="compile + run fixture under qemu-riscv64 -strace")
    rv.add_argument("fixture", nargs="?", help="path to fixtures/*.c")
    rv.add_argument("--all", action="store_true", help="capture every fixture")
    rv.add_argument("--out", default=str(CORPUS / "rv64_syscalls.jsonl"))

    gu = sub.add_parser("guest", help="run a command in the guest under strace")
    gu.add_argument("command", help="shell command to trace")
    gu.add_argument("--name", required=True, help="corpus record name")
    gu.add_argument("--out", default=str(CORPUS / "guest_syscalls.jsonl"))

    args = ap.parse_args()
    if args.mode == "rv64":
        fixtures = ([*FIXTURES.glob("*.c")] if args.all else [Path(args.fixture)])
        for fx in fixtures:
            res = capture_rv64(fx, Path(args.out))
            r = res["record"]
            print(f"[rv64] {r['fixture']}: rc={r['rc']} "
                  f"syscalls={len(r['syscalls'])} raw={res['raw']}")
    else:
        res = capture_guest(args.command, args.name, Path(args.out))
        r = res["record"]
        print(f"[guest] {r['fixture']}: rc={r['rc']} "
              f"syscalls={len(r['syscalls'])} raw={res['raw']}")


if __name__ == "__main__":
    main()
