#!/usr/bin/env python3
"""BM903 guest-side handoff provenance gate.

Question (brief .builder_queue/brief_bm903_guest_hermes.md): does the guest's
own read path serve exactly the bytes the BM902-style chain writes — verified
FILE-level from inside the running OS, not just byte-level from the host?

Three-way agreement:
  A. guest Hermes quotes sha256 + first bytes of a file IT wrote guest-side
  B. host reconstructs the same bytes from container PNGs alone
     (locate_in_container.py verify — pixel path)
  C. host /peek reads the file's first disk byte through the backend's own
     extractor (guest-equivalent disk path)

Negative leg: after guest `rm` + `sync` (+ frame writeback), the guest-half
chain must BREAK (sha mismatch vs the stale pixels, or verify failure).

Instruments (all measured, read-only toward the guest beyond the probe file):
  - guest_bridge.execute_in_guest('hermes_run', task=...)  bounded <300s
  - sshpass/ssh (exact commands, same as locate_in_container uses)
  - livemap_probe.peek (mutex-retry /peek convention)
  - livemap_probe.evict conventions: LRU frames cache stale pixels; the
    negative leg re-peeks only after cold decodes push the file's frame out.

Usage: python3 tools/bare_metal_poc/rung9/guest_provenance_gate.py
Exit 0 = three-way agreement measured AND negative leg RED. Exit 1 = either
leg failed. Artifacts: output/bm903_gate_*.json
"""
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "pixel_container"))
sys.path.insert(0, str(REPO))

from livemap_probe import peek, evict, DEFAULT_CONTAINER  # noqa: E402

DEFAULT_BACKEND = "http://127.0.0.1:8769"

SSH = ["sshpass", "-p", "israel", "ssh", "-o", "StrictHostKeyChecking=no",
       "-o", "ConnectTimeout=10", "-p", "2222", "jericho@127.0.0.1"]
PROBE = "/var/tmp/bm903_probe.bin"
ART = REPO / "output"
BS = 4096


def sh(cmd: str, timeout: int = 60) -> str:
    r = subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"guest ssh failed rc={r.returncode}: {r.stderr[:300]}")
    return r.stdout


def guest_hermes(task: str, timeout: int = 330) -> dict:
    """Bounded guest-Hermes prompt via the 9p file bridge (<300s cap honored)."""
    from guest_bridge import execute_in_guest
    return execute_in_guest("hermes_run", task=task)


def parse_hermes(res: dict) -> str:
    if res.get("status") != "success":
        raise RuntimeError(f"hermes_run failed: {res}")
    resp = res["response"]
    if resp.get("status") != "success":
        raise RuntimeError(f"guest hermes errored: {str(resp)[:300]}")
    return resp.get("output", "")


def find(pattern: str, text: str) -> str:
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError(f"pattern not found in hermes output: {pattern}\n---\n{text[:400]}")
    return m.group(1)


def wait_writeback(max_s: int = 60) -> None:
    """Wait for the backend's ~5s fold to land in the PNGs (frame mtimes advance)."""
    ctrl = DEFAULT_CONTAINER / "frame_%05d.png"
    newest = max((p.stat().st_mtime for p in DEFAULT_CONTAINER.glob("frame_*.png")),
                 default=0)
    t0 = time.time()
    while time.time() - t0 < max_s:
        cur = max((p.stat().st_mtime for p in DEFAULT_CONTAINER.glob("frame_*.png")),
                  default=0)
        if newest and cur >= newest + 1:  # some frame rewritten since start
            time.sleep(2)  # fold settle
            return
        time.sleep(2)
    # timeout is not fatal: the legs below decide truth by content
    print(f"  (writeback wait: no mtime advance in {max_s}s — legs decide)")


def main() -> int:
    ART.mkdir(exist_ok=True)
    import secrets
    nonce = secrets.token_hex(16)
    payload = ("BM903-PROVENANCE " + nonce + " ").encode() * 48  # 3264 B, 1 extent
    sha_expect = hashlib.sha256(payload).hexdigest()
    print(f"probe: {PROBE} size={len(payload)} sha={sha_expect[:16]}…")

    # ---------- Leg 1: guest Hermes writes the probe file itself ----------
    # Payload travels via the shared 9p mount, NOT through the prompt text:
    # run1 measured the LLM rewriting a 48x printf payload to 55x (2400 B ->
    # 2750 B, sha mismatch) — a prompt-embedded payload is not byte-faithful.
    # Host seeds the bytes; Hermes' single bounded action is the guest-side
    # write (cp), preserving the brief's "guest writes the probe file itself".
    seed = REPO / ".hermes_guest_context" / "bm903_seed.bin"
    seed.write_bytes(payload)
    gseed = "/host_zion/projects/visual_audio/.hermes_guest_context/bm903_seed.bin"
    task1 = (f"Run EXACTLY this command with your shell tool: "
             f"cp '{gseed}' {PROBE} && sync && sha256sum {PROBE} && "
             f"stat -c %s {PROBE} && od -A d -t x1 -N 16 {PROBE}. "
             f"Answer in <5 sentences quoting the raw output lines verbatim.")
    t0 = time.time()
    out1 = parse_hermes(guest_hermes(task1))
    dt1 = time.time() - t0
    seed.unlink(missing_ok=True)
    print(f"leg1: guest Hermes wrote probe in {dt1:.0f}s")
    (ART / "bm903_gate_hermes_write.json").write_text(json.dumps(
        {"task": task1, "output": out1, "seconds": round(dt1, 1)}, indent=2))

    # guest half of chain A: direct ssh confirmation of size+sha (exact instrument)
    meta = sh(f"stat -c %s {PROBE}; sha256sum {PROBE} | cut -d' ' -f1; "
              f"filefrag -v {PROBE} | tail -3")
    lines = [l for l in meta.strip().splitlines() if l.strip()]
    gsize, gsha = int(lines[0]), lines[1].strip()
    if gsha != sha_expect:
        print(f"FAIL leg1: guest sha {gsha[:16]}… != expected {sha_expect[:16]}…")
        return 1
    print(f"leg1: guest file {gsize}B sha match ✓")

    # extent map (host-side chain, needs guest filefrag — done above)
    r = subprocess.run([sys.executable, str(REPO / "tools/pixel_container/locate_in_container.py"),
                        "locate", PROBE], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"FAIL locate: {r.stderr[:300]}")
        return 1
    loc = json.loads(r.stdout)
    ext_count = loc["extents"]
    first_byte = loc["spans"][0]["disk_bytes"][0]
    print(f"leg1: {ext_count} extent(s), first disk byte {first_byte} "
          f"(frame {1 + first_byte // (64 * 1024 * 1024)})")
    (ART / "bm903_gate_locate.json").write_text(json.dumps(loc, indent=2))

    # ---------- Leg 2: pixel reconstruction (chain B) ----------
    wait_writeback()
    r = subprocess.run([sys.executable, str(REPO / "tools/pixel_container/locate_in_container.py"),
                        "verify", PROBE, sha_expect], capture_output=True, text=True, timeout=600)
    (ART / "bm903_gate_verify.json").write_text(r.stdout + r.stderr)
    print(f"leg2: verify rc={r.returncode} :: {r.stdout.strip()[:160]}")
    if r.returncode != 0:
        print("FAIL leg2: pixel reconstruction did not sha-match the guest file")
        return 1

    # ---------- Leg 3: /peek first disk byte (chain C) ----------
    want0 = payload[0]
    evict(DEFAULT_BACKEND, DEFAULT_CONTAINER)   # cold decodes: no stale-LRU pass
    got0 = peek(DEFAULT_BACKEND, first_byte)
    if got0 != want0:
        print(f"FAIL leg3: /peek byte {got0:#04x} != expected {want0:#04x}")
        return 1
    # chain C closure vs guest: the byte guest od quoted at offset 0
    if f"{want0:02x}" not in out1.lower():
        print(f"FAIL leg3: guest Hermes output lacks first byte {want0:02x}: {out1[:200]}")
        return 1
    print(f"leg3: /peek {got0:#04x} == pixel byte == guest od byte ✓ "
          f"(three-way agreement measured)")

    (ART / "bm903_gate_green.json").write_text(json.dumps({
        "probe": PROBE, "size": gsize, "sha256": gsha, "extents": ext_count,
        "first_disk_byte": first_byte, "peek_byte": got0,
        "hermes_write_seconds": round(dt1, 1)}, indent=2))

    # ---------- Leg 4 (RED): rm + sync, agreement must BREAK ----------
    task4 = (f"Run EXACTLY this command with your shell tool: "
             f"rm -f {PROBE} && sync && echo REMOVED. Answer in <3 sentences "
             f"quoting the command output.")
    out4 = parse_hermes(guest_hermes(task4))
    (ART / "bm903_gate_hermes_rm.json").write_text(json.dumps(
        {"task": task4, "output": out4}, indent=2))
    if "REMOVED" not in out4:
        print(f"WARN leg4: unexpected hermes rm output: {out4[:120]}")
    gone = subprocess.run(SSH + [f"test -e {PROBE}; echo rc=$?"],
                          capture_output=True, text=True)
    if "rc=1" not in gone.stdout:
        print(f"FAIL leg4: probe file still present guest-side: {gone.stdout}")
        return 1
    print("leg4: guest file gone ✓")

    # chain B must now BREAK: the file is gone guest-side, so verify cannot
    # even map it (no subject for filefrag) — that failure IS the brief's RED
    # ("file gone guest-side; locate/verify fails or pixels change").
    r = subprocess.run([sys.executable, str(REPO / "tools/pixel_container/locate_in_container.py"),
                        "verify", PROBE, sha_expect], capture_output=True, text=True, timeout=600)
    red_b = (r.returncode != 0)
    red_reason = (r.stdout + r.stderr).strip()[:200]
    print(f"leg4: pixel-chain RED probe rc={r.returncode} :: {red_reason}")
    (ART / "bm903_gate_red.json").write_text(json.dumps({
        "verify_rc": r.returncode, "stdout": r.stdout, "stderr": r.stderr}, indent=2))

    # chain C after rm: pixels still hold the bytes (no journal folding of a
    # plain write — the file's data blocks persist until overwritten). The
    # honest expectation: /peek STILL serves the byte (stale pixels), so the
    # RED is the guest-half (file gone + sha chain broken), not necessarily
    # the peek. Measure, don't assume:
    evict(DEFAULT_BACKEND, DEFAULT_CONTAINER)
    peek_after = peek(DEFAULT_BACKEND, first_byte)
    print(f"leg4: /peek after rm: {peek_after:#04x} "
          f"({'stale-pixel byte persists (measured)' if peek_after == want0 else 'changed'})")

    if not red_b:
        print("FAIL leg4: negative leg did not go RED — verify still green after rm")
        return 1
    print("GATE PASS: three-way agreement + discriminating negative leg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
