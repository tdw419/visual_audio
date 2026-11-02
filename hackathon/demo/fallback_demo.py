"""h7 — fallback demo: the classical (non-SAM) decode path, standalone.

Demo-day insurance (settle day, no new features): if the live SAM-3.1 call
is unavailable or returns a low-confidence segmentation (wire score below
the h4 CONF_THRESHOLD gate), the classical pixel decode path from h4 is the
fallback. This script runs THAT path alone against the committed lowconf
fixtures, byte-checked against the fixture ground truth, with wall-time
accounted against the h6 decode budget.

One command: hackathon/demo/freeze/FALLBACK_DEMO.sh
"""
import hashlib
import json
import pathlib
import time

DEMO_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parent.parent
FIXTURES = REPO_ROOT / "hackathon" / "tests" / "fixtures"

# h6 receipt budget for the decode leg (decode <= 5s).
DECODE_BUDGET_S = 5.0

LOWCONF_RESPONSE = FIXTURES / "glyph_response_lowconf.json"
LOWCONF_POSTER = FIXTURES / "glyph_poster_lowconf.png"
LOWCONF_GT = FIXTURES / "glyph_poster_lowconf.json"

# Sentinel: pass poster_png=None explicitly to run WITHOUT a poster (the
# "live SAM down and nothing to fall back on" negative path).
_DEFAULT = object()


def _failure(gt, gt_md5, t0, error):
    wall = time.monotonic() - t0
    return {
        "ok": False,
        "path": None,
        "payload_md5": None,
        "payload_len": None,
        "gt_md5": gt_md5,
        "otsu_eta": None,
        "wire_score": gt["wire_score"],
        "wall_s": round(wall, 3),
        "within_budget": wall <= DECODE_BUDGET_S,
        "error": error,
    }


def run_fallback_demo(response=None, poster_png=_DEFAULT):
    """Classical decode path on the committed lowconf fixtures.

    Returns {"ok", "path", "payload_md5", "payload_len", "gt_md5",
    "otsu_eta", "wire_score", "wall_s", "within_budget", "error"?}.
    A DecodeError (tamper, missing poster, framing) is SURFACED as
    ok=False + error — never swallowed.
    """
    from hackathon.demo import glyph_decoder

    if response is None:
        response = json.loads(LOWCONF_RESPONSE.read_text())
    if poster_png is _DEFAULT:
        poster_png = LOWCONF_POSTER.read_bytes()  # decoder contract: PNG bytes
    gt = json.loads(LOWCONF_GT.read_text())
    gt_md5 = gt["payload_md5"]

    t0 = time.monotonic()
    try:
        result = glyph_decoder.decode_poster_auto(response, poster_png)
    except glyph_decoder.DecodeError as e:
        return _failure(gt, gt_md5, t0, str(e))
    except Exception as e:  # h7: a demo wrapper NEVER tracebacks on demo day
        return _failure(gt, gt_md5, t0,
                        f"{type(e).__name__}: {e}")
    wall = time.monotonic() - t0
    payload = result["payload"]
    md5 = hashlib.md5(payload).hexdigest()
    return {
        "ok": result["path"] == "pixels" and md5 == gt_md5,
        "path": result["path"],
        "payload_md5": md5,
        "payload_len": len(payload),
        "gt_md5": gt_md5,
        "otsu_eta": result.get("otsu_eta"),
        "wire_score": gt["wire_score"],
        "wall_s": round(wall, 3),
        "within_budget": wall <= DECODE_BUDGET_S,
    }


def main():
    import argparse

    ap = argparse.ArgumentParser(description="h7 fallback demo (classical decode)")
    ap.add_argument("--out-dir", default=None,
                    help="optional directory for summary.json")
    args = ap.parse_args()
    summary = run_fallback_demo()
    if args.out_dir:
        out = pathlib.Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(
        "FALLBACK DEMO %s: path %s | payload md5 %s | gt %s | eta %s | %.3fs wall"
        % (
            "PASS" if summary["ok"] else "FAIL",
            summary["path"],
            summary["payload_md5"],
            summary["gt_md5"],
            ("%.6f" % summary["otsu_eta"]) if summary["otsu_eta"] is not None else "n/a",
            summary["wall_s"],
        )
    )
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
