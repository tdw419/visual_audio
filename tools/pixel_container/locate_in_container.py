#!/usr/bin/env python3
"""locate_in_container — map guest files to PXC1 pixel coordinates, or verify them.

The address chain (all links measured, see docs/GUEST_AGENT_PIXEL_WORKFLOW.md):
    guest file
      -> filefrag -v extents (physical blocks)          [guest, no root needed]
      -> disk byte  = block*4096 + vda3_start*512       [/sys/class/block/vda3/start]
      -> frame      = 1 + byte // 64MiB                 [PXC1: frame 0 = metadata]
      -> intra      = byte % 64MiB
      -> x,y,channel = (intra % 16384)//4, intra//16384, intra%4   [RGBA row-major]

Subcommands:
    locate <guest_path>                 print frame/pixel/channel extent map (JSON)
    verify <guest_path> <sha256|file:>  reconstruct bytes from container PNGs alone,
                                        sha256 them, compare. Exit 0 iff match.
    watch                               one shot: list dirty frames pending writeback

Requires: guest reachable via `sshpass -p israel ssh -p 2222 jericho@127.0.0.1`
(configurable); container dir with frame_%05d.png + header.json.

Verified n=4 (2026-09-16): 17-byte marker (byte-exact @(2048,1161) chR),
108-byte random file (frame 129), 160MiB 2-extent random file crossing 3 frame
boundaries with the 16MiB ext4 allocation gap correctly skipped — sha256
identical guest-side vs container-reconstructed, zero drift. n=4 = independent
777-byte random reproduction by a second agent. Robustness: guest commands
retry w/ backoff (TRANSIENT-EXHAUSTED on real exhaustion), ext4 DELAYED
ALLOCATION on freshly-written files is detected (physical-0 placeholder),
auto-synced and refetched — this, not SSH truncation, caused both n=4 first-
attempt crashes; tmpfs paths fail with an explicit message (their blocks are
RAM, not container pixels), writeback barrier verifies ok:true or warns loudly.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys, time
from pathlib import Path
import numpy as np
from PIL import Image

DEFAULT_CONTAINER = Path("/home/jericho/projects/zion/projects/visual_audio/ubuntu_desktop_pxc1_v3_selfhost")
DEFAULT_SSH = ["sshpass", "-p", "israel", "ssh", "-o", "StrictHostKeyChecking=no",
               "-o", "ConnectTimeout=15", "-p", "2222", "jericho@127.0.0.1"]
BS = 4096
BYTES_PER_FRAME = 64 * 1024 * 1024
ROOTFS_FRAME0 = 1
CONTROL_STRING = b"GNU GRUB"  # cheap falsifier: must be findable if scan path is sane


def ssh_run(cmd: str, ssh: list[str], attempts: int = 3) -> str:
    """Run a guest command with retry/backoff. Transient SSH failures (connection
    blips, truncated output under load) retry before failing; exhaustion exits
    with a TRANSIENT marker so callers never confuse flake with corruption."""
    for i in range(attempts):
        try:
            r = subprocess.run(ssh + [cmd], capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            r = None
        if r is not None and r.returncode == 0:
            return r.stdout
        if i + 1 < attempts:
            time.sleep(1 + i)
    sys.exit(f"TRANSIENT-EXHAUSTED: guest command failed after {attempts} attempts "
             f"(guest up? backend load?): {cmd!r}")


class FragUnstable(Exception):
    pass


def guest_meta(guest_path: str, ssh: list[str]) -> dict:
    fstype = ssh_run(f"stat -f -c %T $(dirname {guest_path})", ssh).strip()
    if "ext" not in fstype.lower():
        sys.exit(f"FATAL: {guest_path} lives on {fstype} (RAM/overlay-backed) — its "
                 "blocks are not in the pixel container. Use a disk-backed path "
                 "such as /var/tmp (see docs/GUEST_AGENT_PIXEL_WORKFLOW.md).")
    # filefrag over SSH can show transient states; the important one is ext4
    # DELAYED ALLOCATION: a freshly-written file has no physical blocks yet and
    # filefrag emits a placeholder (physical block 0 / zero-length row). That
    # crash misled two independent sessions (n=4 first attempts) before being
    # diagnosed. Handle: detect signature, force allocation with sync, refetch.
    ff = ""
    attempt = 0
    while True:
        ff = ssh_run(f"filefrag -v {guest_path}", ssh)
        try:
            size_m = re.search(r"^File size of \S+ is (\d+)", ff, re.M)
            if not size_m:
                raise FragUnstable("no header line")
            size = int(size_m.group(1))
            extents = []
            for m in re.finditer(r"^\s*\d+:\s*(\d+)\.\.\s*(\d+):\s*(\d+)\.\.\s*(\d+):\s*(\d+)", ff, re.M):
                l0, l1, p0, p1, ln = map(int, m.groups())
                # delalloc check MUST precede the arithmetic invariant: ext4's
                # placeholder row (physical 0..0, length 0) violates l1-l0+1==ln
                # by construction, so the invariant check would mask it.
                if p0 == 0 and p1 == 0 and ln <= 1:
                    raise FragUnstable("ext4 delayed allocation (physical block 0 "
                                       "placeholder — file not yet allocated)")
                if l1 - l0 + 1 != ln or p1 - p0 + 1 != ln:
                    raise FragUnstable(f"extent arithmetic violated: {m.group(0)!r}")
                extents.append({"logical_first": l0, "physical_first": p0, "blocks": ln})
            if not extents:
                raise FragUnstable("no extents parsed")
            break
        except FragUnstable as e:
            attempt += 1
            if "delayed allocation" in str(e) and attempt < 3:
                ssh_run("sync", ssh)  # force ext4 to assign real blocks
                time.sleep(1)
                continue
            if attempt >= 2:
                sys.exit(f"FATAL: filefrag output unstable across retry ({e}) — "
                         "re-run once more; if it persists this is a REAL anomaly, "
                         "not transient SSH noise.")
            time.sleep(1)
    parts = ssh_run("cat /sys/class/block/vda3/start", ssh).split()
    vda3_start = int(parts[0])
    return {"size": size, "extents": extents, "vda3_start_sectors": vda3_start,
            "fstype": fstype,
            "fs_block_size": int(ssh_run("stat -f -c %S " + str(Path(guest_path).parent), ssh))}


class Container:
    def __init__(self, cdir: Path):
        self.cdir = cdir
        self.cache: dict[int, bytes] = {}

    def barrier(self, control_url: str = "http://127.0.0.1:8769/compact_journal",
                max_wait: float = 90.0) -> bool:
        """Make recent guest writes visible in container frame PNGs, then return.
        MEASURED 2026-09-16 (this is the third and deepest staleness trap):
          - /writeback acks ok:true and moves staged journal PNGs, but does NOT
            fold pending write entries into frame PNGs. Verified: fresh guest
            data stayed invisible through 10s of writebacks.
          - /compact_journal IS the fold (entries -> frame PNGs). It acks
            ok:true first and rewrites PNGs asynchronously (34s observed for
            1377 entries), so after a non-zero fold we WAIT for a frame mtime
            to advance past barrier start before trusting reads.
        Returns False with a loud warning if the fold fails or never becomes
        visible; silently stale reads are the failure mode this exists to kill.

        CONCURRENCY INVARIANT (measured 2026-09-16, 4-lane stress, all byte-exact):
        compact_journal SERIALIZES: one fold at a time, ~34s floor per fold
        (1 entry took 33.7s; 1377 took 34.4s). Concurrent fold requests queue.
        A fold processes the ENTIRE journal, so "any frame mtime advanced"
        implies every waiter's entries folded — the global mtime check is
        sound. Revisit only if the backend ever does partial folds.
        Clients must use timeouts > 34s or risk 000/timeout while queued."""
        t0 = time.time()
        r = subprocess.run(["curl", "-s", "-X", "POST", "--max-time", "120", control_url],
                           capture_output=True, text=True, timeout=150)
        if r.returncode != 0 or "true" not in r.stdout:
            print(f"WARNING: compact_journal barrier did not confirm ok:true "
                  f"(rc={r.returncode}, out={r.stdout[:120]!r}) — frames may be "
                  f"STALE.", file=sys.stderr)
            return False
        try:
            folded = json.loads(r.stdout).get("entries_compacted", 0)
        except (ValueError, AttributeError):
            folded = 1  # unparseable ack: assume work may have happened, wait
        if folded == 0:
            return True  # nothing to fold; container is current
        while time.time() - t0 < max_wait:
            pngs = list(self.cdir.glob("frame_*.png"))
            if pngs and max(p.stat().st_mtime for p in pngs) > t0:
                return True  # fold became visible on disk
            time.sleep(1.0)
        print(f"WARNING: fold acked ({folded} entries) but no frame PNG was "
              f"rewritten within {max_wait}s — reads may be STALE.", file=sys.stderr)
        return False

    def stream(self, fno: int) -> bytes:
        if fno not in self.cache:
            a = np.asarray(Image.open(self.cdir / f"frame_{fno:05d}.png"), dtype=np.uint8)
            assert a.shape == (4096, 4096, 4), f"unexpected frame shape {a.shape}"
            self.cache[fno] = a.tobytes()
        return self.cache[fno]

    def read(self, disk_byte: int, n: int) -> bytes:
        out = bytearray()
        while n > 0:
            fno = ROOTFS_FRAME0 + disk_byte // BYTES_PER_FRAME
            intra = disk_byte % BYTES_PER_FRAME
            take = min(n, BYTES_PER_FRAME - intra)
            out += self.stream(fno)[intra:intra + take]
            disk_byte += take
            n -= take
        return bytes(out)


def disk_byte_of(block: int, vda3_start_sectors: int) -> int:
    return block * BS + vda3_start_sectors * 512


def pixel_of(disk_byte: int) -> dict:
    fno = ROOTFS_FRAME0 + disk_byte // BYTES_PER_FRAME
    intra = disk_byte % BYTES_PER_FRAME
    return {"frame": fno, "x": (intra % 16384) // 4, "y": intra // 16384,
            "channel": "RGBA"[intra % 4], "intra_byte": intra}


def cmd_locate(args, meta) -> None:
    v = meta["vda3_start_sectors"]
    spans = []
    for e in meta["extents"]:
        b0 = disk_byte_of(e["physical_first"], v)
        b1 = disk_byte_of(e["physical_first"] + e["blocks"], v)  # exclusive
        spans.append({"disk_bytes": [b0, b1], "start": pixel_of(b0), "end": pixel_of(b1 - 1),
                      "blocks": e["blocks"], "logical_first": e["logical_first"]})
    frames = sorted({s["start"]["frame"] for s in spans} | {s["end"]["frame"] for s in spans})
    print(json.dumps({"guest_path": args.guest_path, "size": meta["size"],
                      "extents": len(spans), "frames": frames, "spans": spans}, indent=1))


def cmd_verify(args, meta) -> None:
    want = args.sha
    if want.startswith("file:"):
        # sha256s.txt format: "<hash>  <name>" — select by basename, not first token
        base = Path(args.guest_path).name
        want = next((h for h, n in (ln.split() for ln in Path(want[5:]).read_text().splitlines() if ln.strip())
                     if n == base), None)
        if want is None:
            sys.exit(f"no sha for {base} in file; entries are '<hash> <name>'")
    want = want.strip().lower()
    v = meta["vda3_start_sectors"]
    chunks = []
    for e in meta["extents"]:
        for i in range(0, e["blocks"], 512):
            step = min(512, e["blocks"] - i)
            chunks.append(c.read(disk_byte_of(e["physical_first"] + i, v), step * BS))
    recon = b"".join(chunks)[:meta["size"]]  # files occupy whole blocks; hash file bytes only
    got = hashlib.sha256(recon).hexdigest()
    ok = got == want
    print(json.dumps({"guest_path": args.guest_path, "size": meta["size"],
                      "recon_sha256": got, "expected_sha256": want,
                      "match": ok,
                      "frames_read": sorted(c.cache.keys()),
                      "note": "container is authoritative only after a writeback barrier" if not ok else "ok"},
                     indent=1))
    sys.exit(0 if ok else 1)


def cmd_watch(args) -> None:
    j = Path("/tmp/pxc1_cow_journal")
    frames = sorted(int(m.group(1)) for p in j.glob("frame_*.png")
                    if (m := re.match(r"frame_(\d+)\.png", p.name)))
    print(json.dumps({"dirty_frames_pending": frames,
                      "note": "backend folds these every ~5s; act fast or barrier first"}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--container", type=Path, default=DEFAULT_CONTAINER)
    ap.add_argument("--ssh-cmd", default=None, help="alternative ssh command (advanced)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_loc = sub.add_parser("locate")
    p_loc.add_argument("guest_path")
    p_ver = sub.add_parser("verify")
    p_ver.add_argument("guest_path")
    p_ver.add_argument("sha", help="sha256 hex, or file:<path> to read from a sha256s file")
    p_ver.add_argument("--no-barrier", action="store_true",
                       help="skip the writeback barrier (faster, may read stale frames)")
    sub.add_parser("watch")
    args = ap.parse_args()
    ssh = args.ssh_cmd.split() if args.ssh_cmd else DEFAULT_SSH
    c = Container(args.container)
    if args.cmd == "watch":
        cmd_watch(args)
    elif args.cmd == "locate":
        cmd_locate(args, guest_meta(args.guest_path, ssh))
    elif args.cmd == "verify":
        meta = guest_meta(args.guest_path, ssh)  # includes sync on delalloc paths
        # ORDERING: data must reach the backend's COW journal BEFORE the barrier
        # folds it into PNGs. For a fresh file the write may still be in guest
        # page cache when guest_meta returns (filefrag shows blocks, data not
        # yet flushed) — so sync, THEN barrier, THEN read. Barrier-first (the
        # old order) verified against stale frames and looked like corruption.
        ssh_run("sync", ssh)
        if not args.no_barrier:
            c.barrier()
        cmd_verify(args, meta)
