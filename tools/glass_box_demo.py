#!/usr/bin/env python3
"""tools/glass_box_demo.py — BK-14: Glass Box End-to-End Demonstration.

Executes the GH-26.5 Glass Box scenario against the committed tree, printing
a stage-by-stage trace of concrete observations and verifying the three anchors:
  1. Frame Geometry (tools.geos_hilbert.verify_reference_pixels)
  2. Admitted Capability (SHA256 of admitted tile in tools/glyph_gpt/admitted/)
  3. Execution Fixpoint (Canonical replay MD5 over 16,384 memory words)

Lifts scenario workflow from tools/gh26_glass_box_scenario.py with explicit
human-gate (GEOS_EMIT_ACK) environment enforcement and detailed evidence output.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.geos_ascii_bridge import project
from tools.geos_emit import GeosEmitter, encode_mailbox_word
from tools.geos_hilbert import stamp_reference_pixels, verify_reference_pixels
from tools.gh26_glass_box_scenario import GOOD_TILE
from tools.glyph_gpt.agent_resident import resident_image
from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.baker import syscall_abi_kernel_image
from tools.glyph_gpt.runner import GlyphRunner

EXPECTED_TILE_SHA = "d29b29043f6dfa1e24c10db63fc7371c944b88140a9dd3527955769e5cdbdc33"
EXPECTED_REPLAY_MD5 = "ab8e4b39afc20d088a001d186c3e2174"


def check_human_gate() -> None:
    """Verify GEOS_EMIT_ACK is set in the environment; refuse if unset."""
    if not os.environ.get("GEOS_EMIT_ACK"):
        sys.stderr.write(
            "REFUSAL: GEOS_EMIT_ACK environment variable is unset.\n"
            "The glass-box demo exercises the agent write path (tools.geos_emit),\n"
            "which is human-gated under GH-26.2 / demo_wc008 governance rules.\n"
            "To authorize execution, set GEOS_EMIT_ACK in your environment:\n"
            "    export GEOS_EMIT_ACK=1\n"
            "or pass inline:\n"
            "    GEOS_EMIT_ACK=1 python3 tools/glass_box_demo.py\n"
        )
        sys.exit(1)


def run_glass_box_demo(work_dir: Optional[Path] = None, show_canvases: bool = False) -> int:
    check_human_gate()
    print("=" * 72 + "\nGLYPH OS GLASS BOX DEMONSTRATION (GH-26.5 / BK-14)\n" + "=" * 72)

    d_ctx = tempfile.TemporaryDirectory() if work_dir is None else None
    root = Path(d_ctx.name if d_ctx else work_dir)
    pub_dir = root / "publish"
    pub_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ── Stage 0: Frame Geometry Self-Attestation (Anchor 1) ───────────
        print("\n[Stage 0] Frame Geometry Self-Attestation (Anchor 1)")
        surface_frame = np.zeros((128, 128, 3), dtype=np.uint8)
        stamp_reference_pixels(surface_frame, n=128)
        geo_diag = verify_reference_pixels(surface_frame, n=128)
        anchor1_ok = geo_diag["ok"] is True
        print(f"  Diagnosis:        {geo_diag['diagnosis']}")
        passed_markers = [k for k, v in geo_diag["markers"].items() if v.get("ok")]
        print(f"  Markers matched:  {', '.join(passed_markers)} (5/5)\n  Anchor 1 Status:  {'PASS' if anchor1_ok else 'FAIL'}\n")
        if not anchor1_ok:
            return 1

        # ── Stage 1: Intent Posted to Mailbox ─────────────────────────────
        print("\n[Stage 1] Intent Posted to Mailbox (tools.geos_emit)")
        emitter = GeosEmitter(publish_dir=pub_dir)
        np.save(pub_dir / "kernel_memory.npy", np.zeros(16384, dtype=np.uint32))
        post_rcpt = emitter.emit({"kind": "post", "box": 2, "word": 750, "op": 0x11, "payload": 0x2A})
        mem_posted = np.load(pub_dir / "kernel_memory.npy")
        w750, expected_w750 = int(mem_posted[750]), encode_mailbox_word(0x11, 0x2A)
        canvas1 = project(mem_posted, w=80, h=25)
        c1_char = canvas1.split("\n")[17][27]
        s1_ok = post_rcpt.get("committed") is True and w750 == expected_w750 and c1_char == ">"
        print(f"  Mailbox word 750: {w750:#010x} (op=0x11, payload=0x2a, cksum=0x3b)")
        print(f"  Hilbert coord:    (27, 17) -> marker '{c1_char}'")
        print(f"  Committed:        {post_rcpt.get('committed')} (checksum {post_rcpt.get('checksum', '')[:12]}...)")
        print(f"  Stage 1 Status:   {'PASS' if s1_ok else 'FAIL'}")
        if show_canvases:
            print("  Canvas slice:\n" + "\n".join(f"    {l[:40]}" for l in canvas1.split("\n")[15:20]))
        if not s1_ok:
            return 1

        # ── Stage 2: Preemptive Servicing by Resident Daemon ──────────────
        print("\n[Stage 2] Preemptive Servicing by Resident Daemon (GH-16 / Tier 3)")
        res_img = root / "gh26_resident.npy"
        resident_image(build_default_atlas(), mode="resident", timer_quantum=12, out_path=res_img)
        drive_res = GlyphRunner(res_img, ram_words=16384).drive(
            seeds={750: expected_w750}, publish_dir=pub_dir, max_instructions=60000)
        mem_res = drive_res["memory"]
        ticks, w754, w703 = int(mem_res[732]), int(mem_res[754]), int(mem_res[703])
        canvas2 = project(mem_res, w=80, h=25)
        lines2 = canvas2.split("\n")
        c2_argv, c2_res, c2_exit = lines2[17][27], lines2[17][29], lines2[24][31]
        s2_ok = (drive_res["halted"] is True and not drive_res["faulted"] and ticks >= 1 and
                 w754 == 126 and w703 == 0xFEED0006 and c2_argv == ">" and c2_res == "@" and c2_exit == "X")
        print(f"  Execution status: halted={drive_res['halted']}, faulted={drive_res['faulted']}")
        print(f"  Ticks serviced:   {ticks} (word 732, GH-16 timer quantum=12)")
        print(f"  Argv preserved:   {int(mem_res[750]):#010x} -> marker '{c2_argv}' @ (27, 17)")
        print(f"  Result computed:  {w754} (3 * 0x2a = 0x7e) -> marker '{c2_res}' @ (29, 17)")
        print(f"  Exit word:        {w703:#010x} -> marker '{c2_exit}' @ (31, 24)")
        print(f"  Stage 2 Status:   {'PASS' if s2_ok else 'FAIL'}")
        if show_canvases:
            print("  Canvas slice:\n" + "\n".join(f"    {l[:40]}" for l in lines2[16:26]))
        if not s2_ok:
            return 1

        # ── Stage 3: Dynamic Capability Admission via Oracle (Anchor 2) ───
        print("\n[Stage 3] Dynamic Capability Admission via Oracle (Anchor 2)")
        admit_img = root / "gh26_admit.npy"
        syscall_abi_kernel_image(build_default_atlas(), mode="admit", timer_quantum=20, out_path=admit_img)
        runner_admit = GlyphRunner(admit_img, ram_words=16384)
        admit_res = emitter.emit_admit(
            runner_admit, GOOD_TILE, sys_n=8, expected=18, argv={0: 6},
            source="template", receipt_path=root / "admissions.jsonl")
        table_word = admit_res.table_word
        tile_sha = hashlib.sha256(GOOD_TILE.encode()).hexdigest()
        admitted_files = list((_REPO / "tools" / "glyph_gpt" / "admitted").glob(f"*{tile_sha[:12]}*.glyph"))
        tile_file = admitted_files[0].name if admitted_files else "none"
        anchor2_ok = (admit_res.ok is True and table_word != 0 and
                      tile_sha == EXPECTED_TILE_SHA and len(admitted_files) >= 1)
        print(f"  Proposal:         syscall 8 (triple verb, expected=18 for argv=6)")
        print(f"  IR / Oracle Gate: ok={admit_res.ok} (code={admit_res.code})")
        print(f"  Table slot 1570:  stamped PC {table_word:#06x}")
        print(f"  Persisted tile:   tools/glyph_gpt/admitted/{tile_file}\n  Tile SHA256:      {tile_sha}")
        print(f"  Anchor 2 Status:  {'PASS' if anchor2_ok else 'FAIL'}\n")
        if not anchor2_ok:
            return 1

        # ── Stage 4: On-Die Re-Dispatch of Admitted Syscall 8 ─────────────
        print("\n[Stage 4] On-Die Re-Dispatch of Admitted Syscall 8")
        drive_admit = runner_admit.drive(seeds={1570: table_word}, publish_dir=pub_dir, max_instructions=60000)
        mem_admit = drive_admit["memory"]
        adm_res_w754 = int(mem_admit[754])
        canvas3 = project(mem_admit, w=80, h=25)
        lines3 = canvas3.split("\n")
        c3_tbl = lines3[21][53]
        s4_ok = (drive_admit["halted"] is True and not drive_admit["faulted"] and
                 adm_res_w754 == 18 and c3_tbl == "T")
        print(f"  Execution status: halted={drive_admit['halted']}, faulted={drive_admit['faulted']}")
        print(f"  Syscall 8 result: {adm_res_w754} @ word 754 (expected 18)")
        print(f"  Table slot 1570:  marker '{c3_tbl}' @ (53, 21)\n  Stage 4 Status:   {'PASS' if s4_ok else 'FAIL'}")
        if show_canvases:
            print("  Canvas slice:\n" + "\n".join(f"    {l[45:65]}" for l in lines3[19:24]))
        if not s4_ok:
            return 1

        # ── Stage 5: Canonical Replay Fixpoint (Anchor 3) ─────────────────
        print("\n[Stage 5] Canonical Replay Fixpoint (Anchor 3)")
        np.save(admit_img, runner_admit.image)
        drive_replay = GlyphRunner(admit_img, ram_words=16384).drive(seeds={1570: table_word}, max_instructions=60000)
        mem_replay = drive_replay["memory"]
        diffs = sum(1 for a, b in zip(mem_admit, mem_replay) if a != b)
        replay_md5 = hashlib.md5(np.array(mem_replay, dtype=np.uint32).tobytes()).hexdigest()
        anchor3_ok = (drive_replay["halted"] is True and not drive_replay["faulted"] and
                      diffs == 0 and replay_md5 == EXPECTED_REPLAY_MD5)
        print(f"  Replay run:       halted={drive_replay['halted']}, faulted={drive_replay['faulted']}")
        print(f"  Divergence:       {diffs} words across 16,384 memory cells\n  Final State MD5:  {replay_md5}")
        print(f"  Anchor 3 Status:  {'PASS' if anchor3_ok else 'FAIL'}\n")
        if not anchor3_ok:
            return 1

        # ── Final Summary: The Three Anchors ──────────────────────────────
        all_passed = anchor1_ok and anchor2_ok and anchor3_ok
        print("\n" + "=" * 72 + "\nTHE THREE ANCHORS (GH-26 Provenance Chain)\n" + "=" * 72)
        print(f"  1. Frame Geometry:      {geo_diag['diagnosis']}\n     Status:              {'PASS' if anchor1_ok else 'FAIL'}")
        print(f"  2. Admitted Capability: SHA256: {tile_sha}\n     Artifact:            tools/glyph_gpt/admitted/{tile_file}\n     Status:              {'PASS' if anchor2_ok else 'FAIL'}")
        print(f"  3. Execution Fixpoint:  MD5: {replay_md5}\n     Status:              {'PASS' if anchor3_ok else 'FAIL'}")
        print("=" * 72)
        print(f"VERDICT: {'ALL THREE ANCHORS VERIFIED (exit 0)' if all_passed else 'VERIFICATION FAILED (exit 1)'}\n")
        return 0 if all_passed else 1
    finally:
        if d_ctx:
            d_ctx.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BK-14 / GH-26.5 Glass Box End-to-End Demonstration")
    parser.add_argument("--work-dir", type=Path, default=None, help="Optional directory for artifacts")
    parser.add_argument("--show-canvases", action="store_true", help="Display ASCII canvas slices for each stage")
    args = parser.parse_args()
    sys.exit(run_glass_box_demo(work_dir=args.work_dir, show_canvases=args.show_canvases))


if __name__ == "__main__":
    main()
