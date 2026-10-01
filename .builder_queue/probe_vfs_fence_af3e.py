#!/usr/bin/env python3
"""probe_vfs_fence_af3e.py — Phase 1c research (BK-45 candidate): the
VFS-ATTACHED syscall twins under a CONTAINED USER task, the arm left
explicitly unmeasured by RESEARCH_fw_exfil_path_read.md:111 and
RESEARCH_fs_allow_asymmetry.md:109-111 ("whether the VFS layer
re-implements or inherits the root check is unmeasured") and by
RESEARCH_parallel_st_fence_bypass.md (BK-39's PUSH/POP/CALL image-plane
leg, whose RAM-grid reach was flagged unproven).

Two questions in one probe, both against the landed GlyphVfs
(tools/glyph_vfs.py) attached via spawn(vfs=...) on the SAME item-29
containment harness as BK-38..44 (tile (5,0,8,8), MODE_USER at first
instruction):

  Q1  THE OPEN FS QUESTION: with a VFS attached, do 0x03/0x04/0x13
      route through vfs_* (which re-implements containment via
      _guest_rel: '..' refused, staging-root resolve) and therefore
      BEHAVE DIFFERENTLY from the host arms BK-44 convicted — i.e. is
      the VFS layer the containment the host arms lack? Legs:
        A vfswrite_relative   0x03 'q1.txt'            -> rc 0, staged
        B vfswrite_escape     0x03 '../../../../tmp/b8w' -> rc -1 refused?
        C vfswrite_absolute   0x03 '/etc' shape '/tmp_abs.txt' -> staged?
        D vfslist_escape      0x13 '..'                -> rc -1?
        E vfslist_root        0x13 '/'                 -> entry count
        F ctl_st_out          plain ST out-of-tile     -> TRAP (E-K1)

  Q2  THE BK-39 OPEN-REACH QUESTION: does PARALLEL_ST (fence-blind,
      measured) let a contained task write the RAM word that the
      handler's dest loop later checks? NO — the dest loop is
      handler-side host code; the guest cannot interleave. Instead the
      measurable guest-side reach is: can the VFS dest loop itself
      write OUT-OF-TILE? Source-read says the 0x03/0x04/0x13 dest loops
      check only 0 <= a < len(memory) — the same fence-blind shape
      BK-40 measured for 0x02/0x04/0x13 host arms. If out-of-tile
      lands via the VFS arm too, BK-40's class EXTENDS to the VFS
      layer (BK-40's probe ran VFS-less; this closes that scope note).
        G vfsread_dest_out   0x04 staged file, dest=168 (OUT-of-tile)
                            -> bytes land out-of-tile? (BK-40 L2 shape,
                               now with VFS attached)
        H vfslist_dest_out   0x13 listing, dest=168  -> same question

Expected (if the source-read is right): A/C/E staged-in-VFS (rc>=0),
B/D REFUSED by _guest_rel (the VFS layer IS contained on paths —
unlike the host arms), while G/H land OUT-OF-TILE (the fence-blind
dest class extends). That combination would be the measured verdict:
VFS path containment real, VFS RAM-dest containment absent — one
boundary enforced, the other not, in the SAME handlers.

GEOMETRY (the documented PARALLEL_ST mirror trap): tile rows 5..11 x
cols 0..7; staged paths <= 9 bytes at words 160.. -> 34 < 40
instructions, clear of mirror row 5 (slots 40..47). In-tile scratch
192..198; out-of-tile dest 168 (row 5 col 8).

Determinism: 3 internal runs, byte-identical results blob, md5 printed.
Run: python3 .builder_queue/probe_vfs_fence_af3e.py
"""
import hashlib
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    MODE_SUPER,
    OpcodeMapV2,
    TILE_H_ADDR,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402
from tools.glyph_vfs import GlyphVfs  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8
STAGE_WORD = 160
RC_WORD = 198                        # in-tile (row 6 col 6)
DATA_WORD = 196                      # in-tile (row 6 col 4)
LIST_DEST = 192                      # in-tile (row 6 col 0)
OUT_DEST = 168                       # OUT-of-tile (row 5 col 8)
TILE_H_WORD = TILE_H_ADDR >> 2

ESCAPE_PATH = "../../"
ABS_HOSTISH = "/tmp/b8w"


def prog_path_tail(path_bytes, sysnum, dest, count):
    """Stage path bytes (each one word), issue SYSCALL sysnum with
    r1=path_addr, r2=dest, r3=count; park rc in RC_WORD; HALT."""
    assert path_bytes.endswith(b"\x00") and len(path_bytes) <= 28
    lines = []
    for i, b in enumerate(path_bytes):
        lines += ["LDI r5 %d" % (STAGE_WORD + i), "LDI r6 %d" % b,
                  "PARALLEL_ST r5 r6 1"]
    lines += ["LDI r1 %d" % STAGE_WORD,
              "LDI r2 %d" % dest,
              "LDI r3 %d" % count,
              "LDI r17 %d" % sysnum,
              "SYSCALL r10 %d" % sysnum,
              "LDI r2 %d" % RC_WORD,
              "ST r2 r10",
              "HALT"]
    return lines


def run_case(label, prog_lines, seed, vfs):
    img = GlyphAssemblerV2(OM).assemble(prog_lines, width_instrs=8)
    table = GlyphProcessTable()
    pid = table.spawn(img, name=label, tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W),
                      vfs=vfs, vfs_shared=True)
    cpu = table.tasks[pid]["cpu"]
    for addr, val in seed.items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    try:
        rc = table.wait(pid)
    finally:
        pass
    return {
        "label": label,
        "rc": rc,
        "rc_name": "EXIT_OK" if rc == EXIT_OK else
                   ("EXIT_FAULT" if rc == EXIT_FAULT else f"?{rc}"),
        "faulted": bool(cpu.faulted),
        "fault_addr": int(getattr(cpu, "fault_addr", 0) or 0),
        "syscall_rc": "%08x" % (int(cpu.memory[RC_WORD]) & 0xFFFFFFFF),
        "out_dest": bytes(cpu.memory[OUT_DEST + i] & 0xFF
                          for i in range(4)).hex(),
        "tile_h_word": int(cpu.memory[TILE_H_WORD]),
        "mode_super": int(cpu.mode) == MODE_SUPER,
    }


def main():
    tmp = tempfile.mkdtemp(prefix="b8probe_")
    png = os.path.join(tmp, "disk.png")
    staged_flag = os.path.join(tmp, "staged.flag")
    try:
        vfs = GlyphVfs.format(png, size_bytes=1 << 20, blocksize=1024)

        p_rel = b"q1.txt\x00"
        p_esc = ESCAPE_PATH.encode() + b"\x00"
        p_root = b"/\x00"
        p_dots = b"..\x00"
        p_abs = ABS_HOSTISH.encode() + b"\x00"

        cases = [
            # A: relative write, dest in-tile -> expect rc 0 staged
            ("vfswrite_relative",
             prog_path_tail(p_rel, 3, DATA_WORD, 2),
             {DATA_WORD: 0x56, DATA_WORD + 1: 0x57, RC_WORD: 0}),
            # B: '..' escape write ('../../' = 6 chars + NUL = 7 bytes = 21
            # staging instrs -> total 28 < 40, clear of the PARALLEL_ST
            # write-through mirror; an earlier draft used a 20-byte path
            # whose 67 instructions self-overwrote the image (measured)
            # — guest can't reach /tmp through the VFS anyway, so any
            # '..'-leading shape exercises _guest_rel's refusal).
            ("vfswrite_escape",
             prog_path_tail(p_esc, 3, DATA_WORD, 2),
             {DATA_WORD: 0x58, DATA_WORD + 1: 0x59, RC_WORD: 0}),
            # B2: absolute HOST-shaped path '/tmp/b8w' (8 chars + NUL = 9
            # bytes = 27 + 7 = 34 < 40, the proven-safe geometry from
            # probe_fs_allow_asym_af3e.py). _guest_rel strips the leading
            # '/' and stages tmp/b8w INSIDE the image — the host /tmp/b8w
            # must NOT appear (measured host-side).
            ("vfswrite_hostabs",
             prog_path_tail(p_abs, 3, DATA_WORD, 2),
             {DATA_WORD: 0x5A, DATA_WORD + 1: 0x5B, RC_WORD: 0}),
            # C: leading-slash absolute shape -> expect staged (single root)
            ("vfswrite_absolute",
             prog_path_tail(b"/abs.txt\x00", 3, DATA_WORD, 2),
             {DATA_WORD: 0x41, DATA_WORD + 1: 0x42, RC_WORD: 0}),
            # D: 0x13 on '..' -> expect rc -1
            ("vfslist_escape",
             prog_path_tail(p_dots, 19, LIST_DEST, 64),
             {LIST_DEST: 0, LIST_DEST + 1: 0, RC_WORD: 0}),
            # E: 0x13 on '/' -> expect entry count >= 0
            ("vfslist_root",
             prog_path_tail(p_root, 19, LIST_DEST, 64),
             {LIST_DEST: 0, LIST_DEST + 1: 0, LIST_DEST + 2: 0, RC_WORD: 0}),
            # F: ST control out-of-tile -> TRAP
            ("ctl_st_out",
             ["LDI r2 %d" % OUT_DEST, "LDI r3 4660", "ST r2 r3", "HALT"],
             {}),
            # G: 0x04 staged read, dest OUT-of-tile -> bytes land?
            ("vfsread_dest_out",
             prog_path_tail(p_rel, 4, OUT_DEST, 64),
             {OUT_DEST: 0, OUT_DEST + 1: 0, RC_WORD: 0}),
            # H: 0x13 listing, dest OUT-of-tile -> bytes land?
            ("vfslist_dest_out",
             prog_path_tail(p_root, 19, OUT_DEST, 64),
             {OUT_DEST: 0, OUT_DEST + 1: 0, RC_WORD: 0}),
        ]

        # Order matters: A stages q1.txt so G can read it back; run A
        # first, then B..F, then G/H. (table.spawn is a fresh engine per
        # case; the VFS staging overlay persists across attaches.)
        order = ["vfswrite_relative", "vfswrite_escape", "vfswrite_hostabs",
                 "vfswrite_absolute", "vfslist_escape", "vfslist_root",
                 "ctl_st_out", "vfsread_dest_out", "vfslist_dest_out"]
        by_label = {lbl: (prog, seed) for lbl, prog, seed in cases}

        all_runs = []
        for _ in range(3):
            # fresh VFS per run: same format, staging cleared by new object
            vfs = GlyphVfs.format(png, size_bytes=1 << 20, blocksize=1024)
            results = []
            for lbl in order:
                prog, seed = by_label[lbl]
                results.append(run_case(lbl, prog, seed, vfs))
            # G/H depend on A's staged file within THIS run — satisfied:
            # A ran first in this loop.
            all_runs.append(results)

        for run in all_runs:
            for r in run:
                print(r)
        print("deterministic:",
              all(all_runs[i] == all_runs[0] for i in range(1, 3)))

        r0 = {r["label"]: r for r in all_runs[0]}
        a, b = r0["vfswrite_relative"], r0["vfswrite_escape"]
        b2 = r0["vfswrite_hostabs"]
        c = r0["vfswrite_absolute"]
        d, e = r0["vfslist_escape"], r0["vfslist_root"]
        f, g, h = r0["ctl_st_out"], r0["vfsread_dest_out"], r0["vfslist_dest_out"]

        a_ok = a["syscall_rc"] == "00000000" and vfs.dirty()
        print("VERDICT vfswrite_relative:", "rc 0, staged in overlay"
              if a_ok else f"not confirmed ({a})")
        b_ok = b["syscall_rc"] == "ffffffff" and b["faulted"] is False
        print("VERDICT vfswrite_escape:", "'..' REFUSED by _guest_rel"
              if b_ok else f"NOT REFUSED — escape reached host? ({b})")
        b2_ok = (b2["syscall_rc"] == "00000000"
                 and not os.path.exists("/tmp/b8w"))
        print("VERDICT vfswrite_hostabs:",
              "host-shaped '/tmp/b8w' staged INSIDE the image (host file absent)"
              if b2_ok else f"not confirmed ({b2})")
        esc_landed = os.path.exists("/tmp/b8w")
        c_ok = c["syscall_rc"] == "00000000"
        print("VERDICT vfswrite_absolute:", "leading '/' staged (single-root)"
              if c_ok else f"refused/unconfirmed ({c})")
        d_ok = d["syscall_rc"] == "ffffffff"
        print("VERDICT vfslist_escape:", "'..' REFUSED on 0x13"
              if d_ok else f"NOT REFUSED ({d})")
        e_ok = e["syscall_rc"] not in ("ffffffff",) and e["faulted"] is False
        print("VERDICT vfslist_root:", "root listing served" if e_ok else f"refused ({e})")
        f_ok = f["faulted"] and f["fault_addr"] == OUT_DEST * 4
        print("VERDICT ctl_st_out:", "trapped as required (E-K1 intact)"
              if f_ok else f"NOT TRAPPED ({f})")
        g_out = bytes.fromhex(g["out_dest"])
        g_ok = g["syscall_rc"] != "ffffffff" and g_out[:2] == b"VW"
        print("VERDICT vfsread_dest_out:",
              "staged bytes LANDED OUT-OF-TILE (fence-blind dest class extends to VFS)"
              if g_ok else f"dropped/refused ({g})")
        h_ok = h["syscall_rc"] != "ffffffff" and h["out_dest"] != "00000000"
        print("VERDICT vfslist_dest_out:",
              "listing bytes LANDED OUT-OF-TILE" if h_ok else f"dropped/refused ({h})")

        print()
        print("ESCAPE FILE CHECK: /tmp/b8w exists:", esc_landed)
        if b_ok and b2_ok and d_ok and f_ok:
            print("VFS PATH CONTAINMENT: '..' refused on write and list; "
                  "host-shaped absolute path stays inside the image — the VFS "
                  "layer re-implements the path containment the host arms "
                  "lack (BK-44's open question answered: contained guests "
                  "get path containment ONLY via the VFS).")
        if g_ok or h_ok:
            print("VFS RAM-DEST CONTAINMENT: ABSENT — the dest loops are the "
                  "same fence-blind bounds-only shape BK-40 measured on the "
                  "host arms; the class extends to the VFS layer.")
        blob = repr(all_runs[0]).encode()
        print("results_md5:", hashlib.md5(blob).hexdigest())
    finally:
        # cleanup: staging dirs inside vfs objects are tempdirs; best-effort
        for p in ("/tmp/b8w",):
            if os.path.exists(p):
                os.unlink(p)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
