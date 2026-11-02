"""h4 fixture generator (deterministic, offline, stdlib only).

Emits the decoder-robustness fixture set committed under
hackathon/tests/fixtures/:

  glyph_poster_stylized.png/.json + glyph_response_stylized.json
      UNSEEN payload on a stylized canvas (decorative border, nonzero box
      origin 48,48, non-pure ink/background). Wire score = MEASURED Otsu
      separability (eta) of the poster crop; >= CONF_THRESHOLD so the SAM
      mask path takes it.
  glyph_poster_lowconf.png/.json + glyph_response_lowconf.json
      Degraded poster (deterministic uniform noise) whose measured eta
      lands BELOW CONF_THRESHOLD. The response wire score is that measured
      eta, so the gate trips on a measured property, and the pixels alone
      still decode byte-identically (per-cell majority survives speckle far
      past the gate).
  h4_calibration.md
      The measured sweep behind CONF_THRESHOLD — regenerated, not hand-written.

Run: /usr/bin/python3.12 hackathon/demo/glyph_fixtures_h4.py [outdir]
"""
import hashlib
import json
import pathlib
import sys

from hackathon.demo import glyph_decoder, glyph_poster

BORDER = 48
BOX = {"x1": BORDER, "y1": BORDER,
       "x2": BORDER + glyph_poster.FRAME_W, "y2": BORDER + glyph_poster.FRAME_H,
       "w": glyph_poster.FRAME_W, "h": glyph_poster.FRAME_H}
POINT = {"x": 300, "y": 300, "label": 1}

PAYLOAD_STYLIZED = b"stylized h4 poster: point-prompt decoded this unseen frame\n"
PAYLOAD_LOWCONF = b"low-confidence fallback: classical pixel decode recovered this payload\n"
LOWCONF_SEED = "h4-lowconf"
SCAN_STEP = 4
GATE = glyph_decoder.CONF_THRESHOLD

FIXTURE_NAMES = [
    "glyph_poster_stylized.png", "glyph_poster_stylized.json",
    "glyph_response_stylized.json",
    "glyph_poster_lowconf.png", "glyph_poster_lowconf.json",
    "glyph_response_lowconf.json",
    "h4_calibration.md",
]


def _crop(rows):
    """The canonical frame inset inside the stylized canvas."""
    return [r[BORDER:BORDER + glyph_poster.FRAME_W]
            for r in rows[BORDER:BORDER + glyph_poster.FRAME_H]]


def _eta(rows):
    return glyph_decoder.otsu(_crop(rows))[1]


def _response(grid, score):
    text = (
        "<0f>0"
        f"<|point;x={POINT['x']};y={POINT['y']};label={POINT['label']}|>"
        + "<|box;x1=%d;y1=%d;x2=%d;y2=%d;w=%d;h=%d|>"
        % (BOX["x1"], BOX["y1"], BOX["x2"], BOX["y2"], BOX["w"], BOX["h"])
        + f"<|score;v={score:.4f}|>"
        + f"<|mask;x=0;y=0;data={glyph_poster.cells_to_rle(grid)}|>"
    )
    return {
        "model": "sam-3.1",
        "status": "completed",
        "object": "response",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


def _gt(payload, png, eta, score, decode_path, extra):
    framed = glyph_poster.frame_payload(payload)
    gt = {
        "canonical_frame": {
            "origin": "top-left",
            "width_px": glyph_poster.FRAME_W,
            "height_px": glyph_poster.FRAME_H,
            "cell_px": glyph_poster.CELL_PX,
            "grid": glyph_poster.GRID,
            "hilbert_order": glyph_poster.HILBERT_ORDER,
        },
        "canvas": "stylized: 48px decorative border, ink 0x08, background 0xF4",
        "payload_hex": payload.hex(),
        "payload_md5": hashlib.md5(payload).hexdigest(),
        "framed_hex": framed.hex(),
        "framed_md5": hashlib.md5(framed).hexdigest(),
        "poster_png_md5": hashlib.md5(png).hexdigest(),
        "otsu_eta": round(eta, 6),
        "wire_score": round(score, 4),
        "conf_threshold": GATE,
        "decode_path": decode_path,
        "box": BOX,
        "point": POINT,
        "bit_encoding": glyph_poster.build_fixtures(payload)["bit_encoding"],
        "framing": glyph_poster.build_fixtures(payload)["framing"],
        "mask_wire": glyph_poster.build_fixtures(payload)["mask_wire"],
    }
    gt.update(extra)
    return gt


def _sweep(base_rows, payload, levels):
    """Measured (level, eta, decodes_ok) rows for the calibration note."""
    out = []
    for level in levels:
        if level == 0:
            rows = base_rows
        else:
            rows = glyph_poster.degrade_rows(base_rows, LOWCONF_SEED, level)
        eta = _eta(rows)
        png = glyph_poster.png_bytes_rows(rows)
        try:
            got, _ = glyph_decoder.decode_poster_pixels(png, BOX)
            ok = got == payload
        except glyph_decoder.DecodeError:
            ok = False
        out.append((level, eta, ok))
    return out


def build_all(outdir):
    outdir = pathlib.Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # ---- stylized (unseen payload, SAM path, score = measured eta) ----
    grid_s = glyph_poster.payload_to_cells(PAYLOAD_STYLIZED)
    rows_s = glyph_poster.stylized_rows(grid_s, border=BORDER)
    png_s = glyph_poster.png_bytes_rows(rows_s)
    eta_s = _eta(rows_s)
    score_s = round(eta_s, 4)
    if eta_s < GATE:
        raise RuntimeError(f"stylized eta {eta_s:.4f} below gate {GATE} — generator invariant broken")
    resp_s = _response(grid_s, score_s)
    out_s = glyph_decoder.decode_poster_auto(resp_s)  # build-time sanity
    if out_s["payload"] != PAYLOAD_STYLIZED or out_s["path"] != "sam":
        raise RuntimeError("stylized fixture does not decode via the SAM path")
    gt_s = _gt(PAYLOAD_STYLIZED, png_s, eta_s, score_s, "sam",
               {"notes": "unseen stylized input; promptable point + nonzero box origin; "
                         "wire score is the measured Otsu eta of the frame crop"})

    # ---- low-confidence: first speckle level with eta < gate, still exact ----
    grid_l = glyph_poster.payload_to_cells(PAYLOAD_LOWCONF)
    base_rows_l = glyph_poster.stylized_rows(grid_l, border=BORDER)
    eta_base_l = _eta(base_rows_l)
    chosen = None
    level = SCAN_STEP
    while level < 256:
        rows = glyph_poster.degrade_rows(base_rows_l, LOWCONF_SEED, level)
        eta = _eta(rows)
        png_l = glyph_poster.png_bytes_rows(rows)
        try:
            got, _ = glyph_decoder.decode_poster_pixels(png_l, BOX)
            ok = got == PAYLOAD_LOWCONF
        except glyph_decoder.DecodeError:
            ok = False
        if eta < GATE and ok:
            chosen = (level, rows, eta, png_l)
            break
        if not ok:
            raise RuntimeError(f"decode broke at level {level} before eta dropped below gate")
        level += SCAN_STEP
    if chosen is None:
        raise RuntimeError("no speckle level drops eta below the gate with exact decode")
    level_l, rows_l, eta_l, png_l = chosen
    score_l = round(eta_l, 4)
    resp_l = _response(grid_l, score_l)
    out_l = glyph_decoder.decode_poster_auto(resp_l, poster_png=png_l)
    if out_l["path"] != "pixels" or out_l["payload"] != PAYLOAD_LOWCONF:
        raise RuntimeError("lowconf fixture does not take the fallback path")
    gt_l = _gt(PAYLOAD_LOWCONF, png_l, eta_l, score_l, "pixels",
               {"notes": f"deterministic uniform-noise level={level_l} "
                         f"(prob {level_l}/256: pixel replaced by a PRNG byte, seed {LOWCONF_SEED!r}); "
                         f"clean-base eta {eta_base_l:.4f}",
                "speckle_level": level_l,
                "clean_base_otsu_eta": round(eta_base_l, 6)})

    # ---- calibration sweep (measured, deterministic) ----
    sweep = _sweep(base_rows_l, PAYLOAD_LOWCONF,
                   list(range(0, level_l + SCAN_STEP, SCAN_STEP))
                   + [l for l in range(level_l + 2 * SCAN_STEP, 161, 2 * SCAN_STEP)])
    cal = _calibration_md(eta_s, eta_base_l, level_l, eta_l, sweep)

    artifacts = {
        "glyph_poster_stylized.png": png_s,
        "glyph_poster_stylized.json": (json.dumps(gt_s, indent=1) + "\n").encode(),
        "glyph_response_stylized.json": (json.dumps(resp_s, indent=1) + "\n").encode(),
        "glyph_poster_lowconf.png": png_l,
        "glyph_poster_lowconf.json": (json.dumps(gt_l, indent=1) + "\n").encode(),
        "glyph_response_lowconf.json": (json.dumps(resp_l, indent=1) + "\n").encode(),
        "h4_calibration.md": cal.encode(),
    }
    for name, data in artifacts.items():
        (outdir / name).write_bytes(data)
    return {n: hashlib.md5(d).hexdigest() for n, d in artifacts.items()}


def _calibration_md(eta_stylized, eta_base, level, eta_lowconf, sweep):
    lines = [
        "# h4 confidence-gate calibration (measured, regenerated — do not hand-edit)",
        "",
        "Regenerate with:",
        "`/usr/bin/python3.12 hackathon/demo/glyph_fixtures_h4.py <outdir>`",
        "(the committed fixtures must reproduce byte-identically — see",
        "test_h4_fixture_regeneration_tie).",
        "",
        "## Quantity",
        "",
        "`eta` = Otsu between-class variance / total variance over the 512x512",
        "frame crop (glyph_decoder.otsu): measured bimodal separability of the",
        "poster pixels, in [0,1]. The wire score in the h4 fixture responses IS",
        "the measured eta of the corresponding poster — the gate trips on a",
        "measured image property, not a hand-picked number.",
        "",
        "## Gate",
        "",
        f"- CONF_THRESHOLD = {GATE} (glyph_decoder.CONF_THRESHOLD)",
        f"- stylized (clean) poster: measured eta = {eta_stylized:.6f} — ABOVE the gate, SAM path",
        f"- lowconf poster base (no speckle): measured eta = {eta_base:.6f}",
        f"- lowconf poster at chosen speckle level {level}: measured eta = {eta_lowconf:.6f} — BELOW the gate, fallback path",
        "",
        f"{GATE} separates the measured clean value from the measured degraded",
        "value with margin on both sides; it is deliberately conservative — the",
        "sweep below shows the classical fallback keeps decoding byte-identically",
        "well past where eta crosses the gate.",
        "",
        "## Sweep (deterministic uniform-noise degradation, seed 'h4-lowconf')",
        "",
        "level | eta | fallback decodes byte-identically",
        "------|-----|----------------------------------",
    ]
    for lvl, eta, ok in sweep:
        lines.append(f"{lvl:5d} | {eta:.6f} | {'YES' if ok else 'NO'}")
    broken = next((l for l, _, ok in sweep if not ok), None)
    if broken is not None:
        lines += [
            "",
            f"Per-cell majority vote first breaks at speckle level {broken} —",
            f"far past the gate trip at level {level}. The gate is the segmenter's",
            "self-reported confidence proxy (live: predicted IoU); the fallback",
            "contract only requires exact decode AFTER the trip, which the sweep",
            "confirms holds with margin.",
        ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "hackathon/tests/fixtures"
    mds = build_all(out)
    for name, md in sorted(mds.items()):
        print(f"{md}  {name}")
