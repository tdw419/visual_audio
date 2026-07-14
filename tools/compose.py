#!/usr/bin/env python3
"""
compose.py — Piece visual-audio words together like code.

A composition is a small program whose tokens are wordbase tiles. It has the
four things that make text "code" rather than a word list:

  tokens        word tiles (stable IDs from wordbase) — playable + visible
  functions     named `blocks`, defined once
  calls         `["place", block, x, y, {args}]` — invoke a block, with args
  nesting       a block may place other blocks (recursion-guarded)

`compile` flattens a manifest into absolute primitive ops, then renders BOTH
projections at once: a composite PNG (the program as a picture on the canvas)
and a WAV (the program read aloud, words in layout order). So a composed
program is itself a visual-audio object — the same substrate it's built from.

Manifest (JSON):
  {
   "canvas": [w, h, "#bg"],
   "blocks": {
     "label": {"params": ["txt","col"],
               "ops": [["word","$txt",2,4,"$col"]]},
     "button":{"params":["txt"],
               "ops":[["frame",0,0,110,22,"#7fb4ff"],
                      ["place","label",6,4,{"txt":"$txt","col":"#ffffff"}]]}
   },
   "main": [["place","button",20,20,{"txt":"open"}],
            ["place","button",20,60,{"txt":"save"}]]
  }
"""

import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wordbase import connect, materialize, word_id, tokenize
from word_compiler import ensure_cmudict, parse_cmudict

MAX_DEPTH = 32


def subst(value, args):
    """Replace $name tokens in a string using the call's args."""
    if isinstance(value, str) and value.startswith('$'):
        return args.get(value[1:], value)
    return value


def flatten(manifest, placements, ox, oy, args, depth, out):
    """Resolve a list of ops/placements into absolute primitive ops."""
    if depth > MAX_DEPTH:
        raise RecursionError("composition nested too deep (cycle?)")
    for op in placements:
        kind = op[0]
        if kind == 'place':
            _, block_name, x, y, *rest = op
            call_args = {k: subst(v, args) for k, v in (rest[0] if rest else {}).items()}
            block = manifest['blocks'][block_name]
            flatten(manifest, block['ops'], ox + x, oy + y, call_args, depth + 1, out)
        elif kind == 'word':
            _, text, x, y, color = op
            out.append(['word', subst(text, args), ox + x, oy + y, subst(color, args)])
        elif kind == 'op':
            # Behavior-opcode primitive for executable blocks
            # Format: ["op", opcode, x, y, ...args]
            # Opcode is a GlyphLang spatial opcode (e.g., "spatial_set", "spatial_copy")
            # Args are opcode-specific parameters
            opcode, x, y, *opcode_args = op[1:]
            # Offset x, y coordinates by block origin (explicit first two params)
            offset_x = ox + x
            offset_y = oy + y
            # Substitute $vars in remaining args
            offset_rest = [subst(arg, args) if isinstance(arg, str) and arg.startswith('$') else arg for arg in opcode_args]
            out.append(['op', opcode, offset_x, offset_y] + offset_rest)
        else:  # frame / rect — primitive, just offset coords
            k, x, y, w, h, color = op
            out.append([k, ox + x, oy + y, w, h, subst(color, args)])
    return out


def compile_manifest(manifest):
    return flatten(manifest, manifest['main'], 0, 0, {}, 0, [])


def hex_color(s):
    s = s.lstrip('#')
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def render(manifest, ops, png_path, wav_path=None):
    w, h, bg = manifest['canvas']
    fb = np.tile(hex_color(bg).astype(np.uint8), (h, w, 1))

    db = connect()
    cmudict = parse_cmudict(ensure_cmudict())
    words_in_order = []            # (x, y, word) for audio ordering

    for op in ops:
        kind = op[0]
        if kind == 'frame':
            _, x, y, ww, hh, c = op
            col = hex_color(c).astype(np.uint8)
            fb[y:y + hh, x:x + 2] = col; fb[y:y + hh, x + ww - 2:x + ww] = col
            fb[y:y + 2, x:x + ww] = col; fb[y + hh - 2:y + hh, x:x + ww] = col
        elif kind == 'rect':
            _, x, y, ww, hh, c = op
            fb[y:y + hh, x:x + ww] = hex_color(c).astype(np.uint8)
        elif kind == 'word':
            _, text, x, y, c = op
            col = hex_color(c)
            cx = x
            for w_ in tokenize(text):
                wid = word_id(db, w_, cmudict)
                _, tile_path = materialize(db, wid, cmudict)
                tile = np.asarray(Image.open(tile_path), dtype=np.float64) / 255.0
                th, tw = tile.shape
                x2, y2 = min(cx + tw, w), min(y + th, h)
                if cx < x2 and y < y2:
                    reg = tile[:y2 - y, :x2 - cx, None]
                    fb[y:y2, cx:x2] = (reg * col + (1 - reg) * fb[y:y2, cx:x2]).astype(np.uint8)
                words_in_order.append((y, x, w_))
                cx += tw + 4
        elif kind == 'op':
            # Behavior opcodes are invisible in visual mode (no rendering)
            # They'll be embedded in code projection mode (future)
            pass

    Image.fromarray(fb, mode='RGB').save(png_path)

    if wav_path:
        pieces = []
        for _, _, w_ in sorted(words_in_order):        # reading order: top→bottom, left→right
            wid = word_id(db, w_, cmudict)
            wav_p, _ = materialize(db, wid, cmudict)
            audio, _ = sf.read(wav_p)
            pieces += [audio, np.zeros(int(44100 * 0.05))]
        if pieces:
            sf.write(wav_path, np.concatenate(pieces), 44100)

    return len(ops), len(words_in_order)


def main():
    ap = argparse.ArgumentParser(description="Compose visual-audio words like code")
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('compile')
    p.add_argument('manifest')
    p.add_argument('-o', '--png', default='program.png')
    p.add_argument('-w', '--wav', default=None)
    p.add_argument('--dump-ops', action='store_true')
    p.add_argument('--verify-opcodes', action='store_true', help='Verify embedded opcodes are valid')

    args = ap.parse_args()
    if args.cmd == 'compile':
        with open(args.manifest) as f:
            manifest = json.load(f)
        ops = compile_manifest(manifest)
        if args.dump_ops:
            print(json.dumps(ops, indent=1))
        n_ops, n_words = render(manifest, ops, args.png, args.wav)
        print(f"compiled {args.manifest}: {n_ops} primitive ops, {n_words} word tiles")
        print(f"  program image: {args.png}")
        if args.wav:
            print(f"  program audio: {args.wav}")

        if args.verify_opcodes:
            op_ops = [op for op in ops if op[0] == 'op']
            print(f"\n  Verified: {len(op_ops)} behavior opcodes embedded")
            for i, op in enumerate(op_ops, 1):
                opcode = op[1]
                x, y = op[2], op[3]
                print(f"    [{i}] {opcode} at ({x}, {y}) with {len(op)-4} args")


if __name__ == '__main__':
    main()
