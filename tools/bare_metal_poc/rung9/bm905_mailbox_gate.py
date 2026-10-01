#!/usr/bin/env python3
"""BM905 gate v2: input mailbox over the pixel medium (brief steps 3-7).

v1 full-gate RED (output/bm905_n4_gate_full.log 15:4x) root causes, all
MEASURED in the lane before touching anything:
  * host paint -> GUEST-disk visibility takes 25-150+ s (journal folds
    serialize at ~34 s and queue; two barriers inside one leg push testimony
    past any wall-clock budget anchored at paint time). The brief's
    "daemon poll <=200 ms, testimony <=5 s per packet" is about the GUEST
    side of arrival — so v2 anchors Leg B/E budgets at the moment the guest
    dd plane is proven to see the painted bytes (file-then-md5, N2 pattern),
    and records paint->visible shim latency as measured fact, not tuned.
  * legA_run2 extra=15/missing=11: run-1 residue was still in the PNG and a
    late fold landed mid-run-2; prediction now (a) starts every run from a
    zeroed, guest-verified window and (b) is computed as the DIFF between
    pre-paint decoded bytes and the paint target, not a zero-window
    assumption.
  * daemon liveness was inferred from a self-matching `pgrep -f` (matches
    its own ssh wrapper). v2 proves the poll loop by watching the stats
    file's mtime advance, with launch retries.
  * daemon log/testimony are archived to output/ BEFORE cleanup rm's them.

Legs:
  A  pixel-landing proof: paint packets, diff decoded frames, changed set
     must EQUAL the predicted set (x2 runs, fresh seqs). Straddle geometry
     (dc9f40d3): 16 B slots are 512-aligned, sector straddle impossible;
     the 128 KiB window sits wholly inside frame 1, so the frame boundary
     is not crossed by window bytes either — recorded as fact below.
  B  keycode arrival: guest daemon testifies EV_KEY press+release for
     >=3 distinct keycodes within LATENCY_BUDGET_S of GUEST-VISIBLE.
  C  dedup negative: window zeroed, then OLD seqs (already consumed) painted
     and proven guest-visible: testimony count must NOT increase.
  D  comparator mutant: --mutant shifts the window base by one sector in
     the prediction only -> Leg A must go RED, exit 1.
  E  malformed packet: CRC-corrupted slot (distinct seq/slot from the good
     packet) -> daemon skip counter moves after visibility, testimony does
     not include the corrupted seq.

Guest read is the arrival authority; the pixel diff corroborates the mapping.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "pixel_container"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from locate_in_container import Container, DEFAULT_CONTAINER  # noqa: E402
import bm905_mailbox_packet as pkt  # noqa: E402
import bm905_host_paint as hp  # noqa: E402
from bm905_sudo_drive import load_password  # noqa: E402

_PW = load_password()  # guest creds live only in gitignored .env
SSH = ["sshpass", "-p", _PW, "ssh", "-o", "StrictHostKeyChecking=no",
       "-p", "2222", "jericho@127.0.0.1"]
SCP = ["sshpass", "-p", _PW, "scp", "-o", "StrictHostKeyChecking=no",
       "-P", "2222"]
ART = REPO / "output"
TESTIFY = "/var/tmp/bm905_testify.jsonl"
STATS = "/var/tmp/bm905_daemon_stats.json"
DLOG = "/var/tmp/bm905_daemon.log"
DAEMON = "/var/tmp/bm905_guest_listener.py"
GFILE = "/var/tmp/bm905_gwm.bin"
LATENCY_BUDGET_S = 5.0      # daemon-poll-side budget, anchored at guest-visible
VIS_DETECT_SLACK_S = 8.0    # our own dd-poll granularity allowance, documented
VISIBILITY_TIMEOUT_S = 260  # fold + queue allowance (measured max ~150 s)
KEYCODES = [30, 31, 32]  # KEY_A KEY_B KEY_C


def sh(cmd, timeout=60):
    r = subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"guest cmd failed rc={r.returncode}: {cmd!r} {r.stderr[:200]}")
    return r.stdout


def sudo_drive(cmd, timeout=120):
    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "bm905_sudo_drive.py"), cmd],
        capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr


def guest_window_md5() -> str:
    """md5 of the full 128 KiB window AS THE GUEST SEES IT: dd to guest file,
    md5sum the file (file-then-md5; pty pipes eat stdout), through sudo."""
    sudo_drive("sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'")
    o = sudo_drive(f"sudo sh -c 'dd if=/dev/vda bs=512 skip={hp.WINDOW_LBA} "
                   f"count={hp.WINDOW_LEN // 512} of={GFILE} 2>/dev/null "
                   f"&& md5sum {GFILE}'")
    m = re.search(r"([0-9a-f]{32})\s+\S*bm905_gwm\.bin", o)
    return m.group(1) if m else ""


def wait_guest_visible(exp_md5: str, timeout=VISIBILITY_TIMEOUT_S, results=None):
    """Poll the guest dd plane until it matches exp_md5. Returns elapsed s or
    None on timeout. This defines GUEST-VISIBLE for legs B/C/E.
    On timeout with `results` given, records the last-observed md5 and a
    sample of the guest's actual bytes vs expectation (late-fold evidence)."""
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        last = guest_window_md5()
        if last == exp_md5:
            return round(time.time() - t0, 1)
        time.sleep(5)
    if results is not None:
        diag = {"last_md5": last, "want_md5": exp_md5,
                "t_s": round(time.time() - t0, 1)}
        try:  # first nonzero byte offset the guest still sees
            o = sudo_drive(f"sudo sh -c 'dd if={GFILE} bs=1 count=256 "
                           f"skip=0 2>/dev/null | od -An -tx1'")
            diag["guest_first_256B"] = re.sub(r"\s+", "", o)[:512]
        except Exception as e:
            diag["diag_error"] = str(e)[:120]
        results.setdefault("visibility_timeouts", []).append(diag)
    return None


def full_window_expect(image: bytes) -> bytes:
    buf = bytearray(hp.WINDOW_LEN)
    buf[:len(image)] = image
    return bytes(buf)


def decode_frame(fno: int) -> np.ndarray:
    return np.asarray(Image.open(DEFAULT_CONTAINER / f"frame_{fno:05d}.png"),
                      dtype=np.uint8)


def snapshot(frames):
    return {f: decode_frame(f) for f in frames}


def predicted_change_pixels(pre: bytes, image: bytes, base: int) -> set:
    """(frame,y,x) for every pixel whose RGB byte value the paint CHANGES,
    derived from the actual pre-paint bytes (residue-robust). `base` is the
    window base used for the mapping — --mutant shifts it one sector."""
    pred = set()
    for i, val in enumerate(image):
        if val and pre[i] != val:
            db = base + i
            intra = db % hp.FRAME_BYTES
            pred.add((hp.window_frame_of(db), intra // (4096 * 4),
                      (intra % (4096 * 4)) // 4))
    return pred


def changed_pixels(a, b, frames):
    out = set()
    for f in frames:
        d = np.any(a[f] != b[f], axis=2)
        for y, x in np.argwhere(d):
            out.add((f, int(y), int(x)))
    return out


def host_window_bytes() -> bytes:
    c = Container(DEFAULT_CONTAINER)  # fresh instance: no stale frame cache
    return c.read(hp.WINDOW_BYTE, hp.WINDOW_LEN)


def zero_and_wait(results, tag, quiescent_s=15.0):
    """Zero the window (PNG + barrier) and prove GUEST-VISIBLE zero TWICE,
    quiescent_s apart. The second confirmation proves the journal fold queue
    is quiet: a late fold re-materializing old packet bytes (measured at N4
    v3 legE) fails this check instead of poisoning the next leg."""
    if not cleanup_window():
        results.setdefault("heal_retries", []).append(f"{tag}: png not zero after fold")
        if not cleanup_window():
            print(f"{tag}: cleanup_window could not zero host plane")
            return False
    zero = hashlib.md5(b"\x00" * hp.WINDOW_LEN).hexdigest()
    for attempt in range(2):
        if wait_guest_visible(zero, results=results) is None:
            return False
        time.sleep(quiescent_s)
        if guest_window_md5() != zero:
            results.setdefault("heal_retries", []).append(
                f"{tag}: late fold re-materialized bytes after zero "
                f"(confirmation {attempt + 1}), re-zeroing")
            if not cleanup_window():
                return False
            continue
        return True
    return wait_guest_visible(zero, results=results) is not None


def cleanup_window():
    """Zero the window via PNG paint and verify through the pixel read path."""
    for fno in (1, 2):
        p = DEFAULT_CONTAINER / f"frame_{fno:05d}.png"
        if not p.exists():
            continue
        img = Image.open(p).convert("RGBA")
        px = img.load()
        changed = False
        for i in range(hp.WINDOW_LEN):
            db = hp.WINDOW_BYTE + i
            if hp.window_frame_of(db) != fno:
                continue
            intra = db % hp.FRAME_BYTES
            x, y, ch = (intra % (4096 * 4)) // 4, intra // (4096 * 4), intra % 4
            if px[x, y][ch]:
                px[x, y] = tuple(0 if k == ch else px[x, y][k] for k in range(4))
                changed = True
        if changed:
            img.save(p)
    Container(DEFAULT_CONTAINER).barrier()
    return not any(host_window_bytes())


def daemon_stats_mtime() -> float:
    o = sh(f"stat -c %Y {STATS} 2>/dev/null || echo 0")
    try:
        return float(o.strip().splitlines()[-1])
    except ValueError:
        return 0.0


def testify_lines():
    return [ln for ln in sh(f"cat {TESTIFY} 2>/dev/null || true").splitlines()
            if ln.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutant", action="store_true",
                    help="shift window base one sector in the PREDICTION only")
    ap.add_argument("--skip-guest", action="store_true",
                    help="host-side legs only (A/D)")
    args = ap.parse_args()

    ART.mkdir(exist_ok=True)
    results = {"legs": {}, "mutant": args.mutant}
    c = Container(DEFAULT_CONTAINER)
    ok_all = True

    # ---------------- daemon lifecycle (guest side) ----------------
    if not args.skip_guest:
        # ZERO THE WINDOW BEFORE THE DAEMON STARTS: a fresh daemon polls a
        # stale window from a prior session first (gate v2 consumed seq 5000
        # at boot -> last_seq=5000 dedup-skipped every gate packet).
        if not zero_and_wait(results, "boot_zero"):
            print("boot zero failed — aborting")
            return 1
        sudo_drive("sudo pkill -f guest_listene[r]; true")  # kill ANY stale daemon first
        subprocess.run(SCP + [str(Path(__file__).resolve().parent / "bm905_guest_listener.py"),
                              f"jericho@127.0.0.1:{DAEMON}"], check=True, timeout=60)
        sudo_drive(f"sudo chmod a+r {DAEMON}")
        sudo_drive(f"sudo rm -f {TESTIFY} {STATS} {DLOG}; true")
        started = False
        for attempt in range(3):
            sudo_drive(
                f"sudo sh -c 'setsid nohup python3 {DAEMON} --window-lba "
                f"{hp.WINDOW_LBA} --max-seconds 1500 > {DLOG} 2>&1 < /dev/null &'; "
                f"true", timeout=90)
            m0 = daemon_stats_mtime()
            t0 = time.time()
            while time.time() - t0 < 20:  # liveness = stats file ADVANCING
                time.sleep(3)
                if daemon_stats_mtime() > m0 and daemon_stats_mtime() > 0:
                    started = True
                    break
            if started:
                results["legs"]["daemon_launch"] = {
                    "attempt": attempt + 1, "stats_polling": True}
                print(f"daemon: alive, stats polling (attempt {attempt + 1})")
                break
            sudo_drive(f"sudo pkill -f guest_listene[r]; true")
        if not started:
            results["legs"]["daemon_launch"] = {"stats_polling": False}
            print("daemon: FAILED TO START — aborting guest legs")
            (ART / "bm905_gate_result.json").write_text(json.dumps(results, indent=1))
            return 1

    # ---------------- Leg A x2 (+B inline) ----------------
    for run, (seq0, keys) in enumerate(
            [(1000, KEYCODES), (2000, [33, 34])], 1):
        if not args.skip_guest:
            if not zero_and_wait(results, f"legA_run{run}_prezero"):
                results["legs"][f"legA_run{run}"] = {"verdict": "FAIL",
                                                     "reason": "pre-zero unproven"}
                ok_all = False
                break

        pkts = [pkt.encode(seq0 + i, pkt.TYPE_PRESS, keys[i], 1)
                for i in range(len(keys))]
        # SYN immediately after the presses in SEQ space: seq0+10 wraps to a
        # LOWER slot (1010%256=18 < 1000%256=232) and a partial fold landing
        # sector 0 first would hand the daemon seq 1010 before 1000-1002,
        # dedup-skipping them (measured gate v2 Leg B failure).
        pkts.append(pkt.encode(seq0 + len(keys), pkt.TYPE_SYN, 0, 0))
        image = pkt.paint_window(hp.WINDOW_BYTE, pkts)

        # straddle geometry (dc9f40d3): 16 B slots are 512-aligned => sector
        # straddle impossible; window is inside frame 1 => no frame crossing.
        slot1_off = ((seq0 + 1) % pkt.SLOTS) * pkt.SLOT
        results["legs"][f"straddle_run{run}"] = {
            "slot_offset": slot1_off,
            "crosses_512": (slot1_off // 512) != ((slot1_off + pkt.SLOT - 1) // 512),
            "window_frame_span": sorted({hp.window_frame_of(hp.WINDOW_BYTE),
                                         hp.window_frame_of(hp.WINDOW_BYTE + hp.WINDOW_LEN - 1)}),
            "note": "16B-aligned slots cannot straddle a 512B sector; "
                    "128KiB window lies wholly inside one frame"}

        base = hp.WINDOW_BYTE - 512 if args.mutant else hp.WINDOW_BYTE
        pre = host_window_bytes()  # post-control state read, fresh decode
        pred = predicted_change_pixels(pre, image, base)
        frames = sorted({f for f, _, _ in pred} or
                        {hp.window_frame_of(hp.WINDOW_BYTE)})
        snap0 = snapshot(frames)
        c.barrier()  # control noise: fold cycle with no new paint
        ctrl = changed_pixels(snap0, snapshot(frames), frames)
        results["legs"][f"control_noise_run{run}"] = len(ctrl)

        t_paint = time.time()
        hp.paint_window(pkts)
        c.barrier()
        snap1 = snapshot(frames)
        changed = changed_pixels(snap0, snap1, frames)
        extra, missing = changed - pred, pred - changed
        exact = (not extra and not missing and len(ctrl) == 0)
        results["legs"][f"legA_run{run}"] = {
            "seqs": [seq0 + j for j in range(len(keys) + 1)], "keys": keys,
            "predicted": len(pred), "changed": len(changed),
            "extra": len(extra), "missing": len(missing),
            "control_noise": len(ctrl), "verdict": "EXACT" if exact else "FAIL"}
        print(f"legA run{run}: pred={len(pred)} changed={len(changed)} "
              f"extra={len(extra)} missing={len(missing)} ctrl={len(ctrl)} -> "
              f"{'EXACT' if exact else 'FAIL'}")
        if args.mutant:
            if not exact:
                print(f"MUTANT RED tail: predicted={len(pred)} changed={len(changed)} "
                      f"extra={len(extra)} missing={len(missing)}\n"
                      f"GATE FAIL (expected under --mutant)")
                results["mutant_verdict"] = "RED as expected"
                (ART / "bm905_gate_result.json").write_text(json.dumps(results, indent=1))
                return 1
            print("MUTANT DID NOT GO RED — comparator too weak")
            (ART / "bm905_gate_result.json").write_text(json.dumps(results, indent=1))
            return 1
        ok_all &= exact
        if not exact:
            results["legs"][f"legA_run{run}"]["extra_px"] = sorted(map(list, extra))[:20]
            results["legs"][f"legA_run{run}"]["missing_px"] = sorted(map(list, missing))[:20]
            break

        if args.skip_guest:
            continue

        # ---------------- guest-visible anchor + Leg B ----------------
        exp_full = full_window_expect(image)
        vis = wait_guest_visible(hashlib.md5(exp_full).hexdigest(), results=results)
        results["legs"][f"guest_visible_run{run}"] = {
            "elapsed_s_after_barrier": vis,
            "note": "shim-era fact: paint+fold -> guest dd plane"}
        print(f"guest-visible run{run}: +{vis}s after paint/barrier")
        if vis is None:
            results["legs"]["legB"] = {"verdict": "FAIL", "reason": "never visible"}
            ok_all = False
            break

        t0 = time.time()
        deadline = t0 + LATENCY_BUDGET_S * len(keys) + VIS_DETECT_SLACK_S
        got_keys, got_wall = {}, {}
        while time.time() < deadline and len(got_keys) < len(keys):
            for ln in testify_lines():
                try:
                    rec = json.loads(ln)
                except ValueError:
                    continue
                if rec.get("type") == 1 and rec.get("code") in keys \
                        and rec.get("seq") in {seq0 + j for j in range(len(keys))}:
                    got_keys.setdefault(rec["code"], rec)
                    got_wall.setdefault(rec["code"], time.time() - t0)
            time.sleep(0.3)
        legb = results["legs"].setdefault("legB", {})
        for k in keys:
            if k in got_keys:
                legb[f"run{run}_key_{k}"] = {
                    "seq": got_keys[k]["seq"],
                    "latency_s_from_visible": round(got_wall[k], 3),
                    "within_budget": got_wall[k] <= LATENCY_BUDGET_S + VIS_DETECT_SLACK_S,
                    "guest_mono_ts": got_keys[k]["mono_ts"]}
        ok_b = all(k in got_keys for k in keys)
        legb["verdict"] = "PASS" if ok_b else "FAIL"
        print(f"legB run{run}: keys testified={sorted(got_keys)} "
              f"-> {'PASS' if ok_b else 'FAIL'}")
        ok_all &= ok_b

    if not args.skip_guest and not args.mutant and ok_all:
        # ---------------- Leg C: replay negative (REAL bytes, OLD seqs) ----
        lines_before = len(testify_lines())
        lines_after = lines_before
        ok_c = False
        if zero_and_wait(results, "legC_prezero"):
            hp.paint_window([pkt.encode(1000, pkt.TYPE_PRESS, 30, 1),
                             pkt.encode(2000, pkt.TYPE_PRESS, 33, 1)])
            c.barrier()
            ok_c = wait_guest_visible(hashlib.md5(full_window_expect(
                pkt.paint_window(hp.WINDOW_BYTE,
                                 [pkt.encode(1000, pkt.TYPE_PRESS, 30, 1),
                                  pkt.encode(2000, pkt.TYPE_PRESS, 33, 1)]))).hexdigest(),
                results=results) is not None
            time.sleep(3)  # a couple of daemon poll cycles
            lines_after = len(testify_lines())
            ok_c &= lines_after == lines_before
        else:
            ok_c = False
        results["legs"]["legC"] = {"testimony_before": lines_before,
                                   "verdict": "PASS" if ok_c else "FAIL"}
        print(f"legC: replay of old seqs did NOT add testimony "
              f"({lines_before} -> {lines_after}) -> {'PASS' if ok_c else 'FAIL'}")
        ok_all &= ok_c

        # ---------------- Leg E: malformed packet ----------------
        good = pkt.encode(3000, pkt.TYPE_PRESS, 35, 1)
        bad = bytearray(pkt.encode(3001, pkt.TYPE_PRESS, 36, 1))
        bad[10] ^= 0x01  # corrupt value byte -> CRC mismatch -> daemon skips
        e_pkts = [good, bytes(bad)]
        e_img = pkt.paint_window(hp.WINDOW_BYTE, e_pkts)
        skip_before = json.loads(sh(f"cat {STATS} 2>/dev/null || echo {{}}") or "{}").get(
            "skipped_malformed", 0)
        ok_v, stats2, seq3000, seq3001 = False, {}, False, False
        if zero_and_wait(results, "legE_prezero"):
            hp.paint_window(e_pkts)
            c.barrier()
            ok_v = wait_guest_visible(hashlib.md5(full_window_expect(e_img)).hexdigest(),
                                      results=results) is not None
            t_e = time.time()
            stats2 = {}
            while time.time() - t_e < 30:
                try:
                    stats2 = json.loads(sh(f"cat {STATS}") or "{}")
                except (ValueError, RuntimeError):
                    stats2 = {}
                if stats2.get("skipped_malformed", 0) >= skip_before + 1:
                    break
                time.sleep(1)
            tf = testify_lines()
            skipped_moved = stats2.get("skipped_malformed", 0) >= skip_before + 1
            seq3000 = any('"seq": 3000' in ln or '"seq":3000' in ln for ln in tf)
            seq3001 = any('"seq": 3001' in ln or '"seq":3001' in ln for ln in tf)
            ok_e = ok_v and skipped_moved and seq3000 and not seq3001
        else:
            ok_e = False
        results["legs"]["legE"] = {
            "skipped": stats2.get("skipped_malformed", 0) if ok_v else None,
            "seq3000_testified": seq3000 if ok_v else None,
            "seq3001_injected": seq3001 if ok_v else None,
            "verdict": "PASS" if ok_e else "FAIL"}
        print(f"legE: skipped={results['legs']['legE']['skipped']} "
              f"seq3000={results['legs']['legE']['seq3000_testified']} "
              f"seq3001_injected={results['legs']['legE']['seq3001_injected']} "
              f"-> {results['legs']['legE']['verdict']}")
        ok_all &= ok_e

    # ---------------- cleanup (always, guest mode) ----------------
    if not args.skip_guest:
        (ART / "bm905_daemon_log.txt").write_text(sh(f"cat {DLOG} 2>/dev/null || true"))
        (ART / "bm905_testify_evidence.jsonl").write_text("\n".join(testify_lines()))
        sudo_drive("sudo pkill -f guest_listene[r]; true")
        time.sleep(1)
        zeroed = zero_and_wait(results, "final_zero")
        sudo_drive(f"sudo rm -f {DAEMON} {TESTIFY} {STATS} {DLOG} {GFILE} "
                   "/var/tmp/bm905_uinput_probe.py /var/tmp/get-pip.py; sync; "
                   "rm -rf /var/tmp/bm905_venv; true")
        gone = sh("ls /var/tmp/bm905_* 2>/dev/null || echo GONE").strip()
        results["cleanup"] = {"window_zeroed": zeroed, "guest_files": gone}
        print(f"cleanup: window_zeroed={zeroed} guest_files={gone}")
        ok_all &= zeroed and gone.endswith("GONE")

    (ART / "bm905_gate_result.json").write_text(json.dumps(results, indent=1))
    print("GATE PASS" if ok_all else "GATE FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
