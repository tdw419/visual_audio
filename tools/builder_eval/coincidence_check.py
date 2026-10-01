#!/usr/bin/env python3
"""coincidence_check.py — audit accepted draftsman tiles for coincidental correctness.

WHY: the mechanical-sample results showed SHR "passing" 2/6 — but both passes used the
*same* value-as-count bug as the 4 failures; they happened to land on 0 because the input
value's own bit-shift and the correct shift both produced 0 for that particular (k, v).
An acceptance test that only checks ONE (k, v) pair cannot tell a correct implementation
from a wrong one that got lucky on that specific input.

This script re-executes every ACCEPTED tile already on disk against a second,
independently-drawn (k, v) pair for the same op — no model call needed, since the tile
text is already committed in the result JSON. A tile is VERIFIED only if it also produces
the right answer on the fresh pair; otherwise it is COINCIDENCE — it passed the recorded
gate but does not implement the operation.

This does not call the model. It re-runs the already-generated tile text through the same
GlyphCPUv2 oracle (`atlas.run_generated`) used by the original sampler, with the tile's own
K held fixed (the tile hardcodes K via its own LDI) and a fresh V drawn for the check.

Usage:
  python3 tools/builder_eval/coincidence_check.py tools/builder_eval/ollama_tile_sample_shiftrule.json [...]
  python3 tools/builder_eval/coincidence_check.py --seed 99 <file> [file ...]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for p in ("tools", "tools/glyph_gpt"):
    sys.path.insert(0, str(_REPO / p))
from atlas import run_generated  # noqa: E402  (GlyphCPUv2 oracle)


def oracle_r10(src: str) -> tuple[bool, int | None, str | None]:
    r = run_generated(src)
    rf = r.get("registers_full") or []
    got = rf[10] if len(rf) > 10 else None
    return bool(r.get("halted")) and not r.get("faulted"), got, r.get("error")


def reference_expected(op: str, k: int, v: int) -> int | None:
    """Ground truth via the oracle's OWN reference tile, not Python arithmetic —
    same standard the original sampler used, so this check has no independent bug
    from re-deriving the answer differently."""
    ok, got, err = oracle_r10(f"LDI r10 {v}\nLDI r0 {k}\n{op} r10 r0\nRET\n")
    if not ok:
        return None
    return got


def audit_row(row: dict, rnd: random.Random) -> dict:
    op, k, tile = row["op"], row["k"], row["tile"]
    v_fresh = rnd.randint(8, 40)
    while v_fresh == row["v"]:
        v_fresh = rnd.randint(8, 40)

    expected_fresh = reference_expected(op, k, v_fresh)
    if expected_fresh is None:
        return {**row, "coincidence_check": "SKIPPED (reference tile unusable at fresh V)"}

    ok, got_fresh, err = oracle_r10(f"LDI r10 {v_fresh}\n{tile}")
    verified = bool(ok and got_fresh == expected_fresh)
    return {
        **row,
        "coincidence_check": "VERIFIED" if verified else "COINCIDENCE",
        "check_v": v_fresh,
        "check_expected": expected_fresh,
        "check_got": got_fresh,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--seed", type=int, default=4242,
                     help="separate seed from the original sample, so the fresh V is "
                          "genuinely independent of whatever generated the original tasks")
    a = ap.parse_args()

    grand_verified = grand_coincidence = grand_accepted = 0
    for fpath in a.files:
        data = json.loads(Path(fpath).read_text())
        rows = data.get("rows", data if isinstance(data, list) else [])
        accepted = [r for r in rows if r.get("accept")]
        rnd = random.Random(a.seed)
        audited = [audit_row(r, rnd) for r in accepted]

        verified = sum(1 for r in audited if r["coincidence_check"] == "VERIFIED")
        coincidence = sum(1 for r in audited if r["coincidence_check"] == "COINCIDENCE")
        skipped = len(audited) - verified - coincidence

        print(f"=== {fpath}")
        print(f"    accepted on original (k,v): {len(accepted)}")
        print(f"    VERIFIED on a second, independent (k,v):   {verified}")
        print(f"    COINCIDENCE (same tile, fails a 2nd input): {coincidence}")
        if skipped:
            print(f"    skipped (reference unusable at fresh V):   {skipped}")

        by_op: dict[str, list[str]] = {}
        for r in audited:
            by_op.setdefault(r["op"], []).append(r["coincidence_check"])
        for op in sorted(by_op):
            vs = by_op[op]
            v_ct, c_ct = vs.count("VERIFIED"), vs.count("COINCIDENCE")
            flag = "  <-- coincidental, not competence" if c_ct and not v_ct else ""
            print(f"      {op:4s} verified={v_ct} coincidence={c_ct}{flag}")

        out_path = Path(fpath).with_name(Path(fpath).stem + ".coincidence_audit.json")
        out_path.write_text(json.dumps({"source": fpath, "seed": a.seed, "rows": audited}, indent=1) + "\n")
        print(f"    -> {out_path}\n")

        grand_verified += verified
        grand_coincidence += coincidence
        grand_accepted += len(accepted)

    print(f"TOTAL across files: {grand_accepted} accepted -> "
          f"{grand_verified} verified, {grand_coincidence} coincidence "
          f"({100.0 * grand_coincidence / max(grand_accepted, 1):.1f}% of accepts were coincidental)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
