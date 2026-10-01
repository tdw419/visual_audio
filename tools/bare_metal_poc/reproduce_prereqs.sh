#!/usr/bin/env bash
# reproduce_prereqs.sh -- turn a clean `git archive HEAD` of tools/bare_metal_poc
# into the tree the closed rungs' gates actually read.
#
# Why this file exists. Rungs 6, 6.5 and 8 each read bytes that no commit
# carries: rung9's and rung6's BUILD PRODUCTS (stage bins, the 13.6 MB pixel
# payload, the media, rung6/fixtures/). ROADMAP's TASK_BM001 bullet lists them;
# running them by hand on 2026-09-20 reproduced the ancestor payloads
# sha256-identical, which is what made the clean-tree BM653 and BM602 runs
# meaningful. This script is that sequence, so the next clean room is one
# command instead of a paragraph, and so the landmark bytes are checked rather
# than trusted.
#
# It builds; it does not boot. No qemu, no guest, no lane contention.
#
#   usage: cd tools/bare_metal_poc && bash reproduce_prereqs.sh
#
# Measured in a fresh `git archive HEAD` tree, and the four ways to break its
# inputs checked there: rung6_5/evidence/bm653/prereq_pristine.txt
#
# One input is not in git at all: rung7/core.gz (9,260,807 B). Place it at
# rung7/core.gz before running -- the script refuses, with its sha256, if it is
# missing or is not the pinned one. BM903 booked that gap as TASK_BM001's; until
# it lands somewhere durable, this line is the workaround:
#   mkdir -p rung7 && cp /path/to/rung7/core.gz rung7/

set -u
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CORE="$ROOT/rung7/core.gz"
CORE_SHA=7f1e370dd4e489fd76c99f76ed9ddd79fd7e51f23af457b07071b3898bb8b5a2

# file -> sha256 the regeneration has to give back. Each was hashed off the tree
# whose gates are green (RECEIPT_BM903_E2E.md, RECEIPT_BM602.md, RECEIPT_BM653.md).
declare -A LANDMARK=(
  ["rung9/bm903_stage1.bin"]=f0e7d7e1c6ab4536852d3c7de33b5e4136db647d6d46d00019a1bec13d991c7b
  ["rung9/bm903_stage2_px.bin"]=2970d2477792d73f11892c78c7060ed685d910ad37bf861ffb5a36831e0a614d
  ["rung9/bm903_px_payload.bin"]=e6ebe1ab6574a01154551f964e249eea560618d90dbf1c3532460e0dabe4ac0e
  ["rung9/bm903_medium_px.raw"]=c8c30130ddc9a207c896e5ce585e88d1e7a9ca2d3be6bc19b7bd13a9d2aab5b4
  ["rung6/bm602_px_payload.bin"]=e6ebe1ab6574a01154551f964e249eea560618d90dbf1c3532460e0dabe4ac0e
  ["rung6/bm602_medium_px.raw"]=32efd1deca4638f9cb006a1bdd2c0dbfdc42d0d55e92ea7ebd031ec8741e3d95
)
# Opaque on purpose: if a step is dropped, its product is missing or stale and
# the landmark check below says which.
declare -A STEP_OF=(
  ["rung9/bm903_stage1.bin"]="rung9 bm903_mkimg.py"
  ["rung9/bm903_stage2_px.bin"]="rung9 bm903_mkimg_px.py"
  ["rung9/bm903_medium_px.raw"]="rung9 bm903_mkimg_px.py"
  ["rung9/bm903_px_payload.bin"]="rung9 bm903_pxcodec.py"
  ["rung6/bm602_px_payload.bin"]="rung6 bm602_pxcodec.py"
  ["rung6/bm602_medium_px.raw"]="rung6 bm602_mkimg.py"
)
# Some of these steps rewrite files that ARE tracked: the layout includes and
# metadata the asm %includes and the gates read. Regenerating them has to give
# back the committed bytes, or the tree is no longer the one the gates were
# gated on -- so each is hashed before and after, which works with or without a
# .git around it.
TRACKED_GENERATED=(
  rung9/bm903_px_layout.inc rung9/bm903_crc32tab.inc
  rung9/bm903_layout.json rung9/bm903_px_meta.json
  rung6/bm602_px_layout.inc rung6/bm602_px_meta.json
)

fail=0
say() { printf '%s\n' "$*"; }
red() { printf '  [RED ] %s\n' "$*"; fail=$((fail + 1)); }

check_landmark() {
  local rel=$1 want got path
  want=${LANDMARK[$rel]}
  path="$ROOT/$rel"
  if [[ ! -f $path ]]; then
    red "$rel is missing; ${STEP_OF[$rel]} writes it"
    return
  fi
  got=$(sha256sum "$path" | cut -d' ' -f1)
  if [[ $got == "$want" ]]; then
    say "  [OK   ] $(basename "$rel") sha256 ${got:0:16}..., the bytes the gates were gated on"
  else
    red "$rel sha256 ${got:0:16}... != the landed ${want:0:16}... -- ${STEP_OF[$rel]} did not reproduce it. Stop: a row gate run on top of this would be measuring a different ancestor."
  fi
}

if ! command -v nasm >/dev/null; then red 'nasm is required'; fi
if ! command -v python3 >/dev/null; then red 'python3 is required'; fi
if (( fail )); then say 'REFUSE: missing tools'; exit 1; fi

if [[ ! -f $CORE ]]; then
  red "$CORE not found -- it is untracked (TASK_BM001's gap). Copy it in first."
  say "REFUSE: no initrd, nothing can be built"; exit 1
fi
core_got=$(sha256sum "$CORE" | cut -d' ' -f1)
if [[ $core_got != $CORE_SHA ]]; then
  red "rung7/core.gz sha256 ${core_got:0:16}... != the pinned ${CORE_SHA:0:16}..."
  say 'REFUSE: the payload is derived from this file; a different initrd is a different ancestor'
  exit 1
fi
say "core.gz: sha256 ${core_got:0:16}..., the pinned input"

# Order is the one that worked by hand: the medium's own builder first (it wants
# stage1/stage2 assembled), then the codec that writes the payload the ECC row
# replays, then rung6's fork of the codec and its fixture media.
run_step() {
  local dir=$1 script=$2 out rc
  out=$(cd "$ROOT/$dir" && python3 "$script" 2>&1); rc=$?
  if (( rc != 0 )); then
    red "$dir/$script exited $rc"
    printf '%s\n' "$out" | tail -4 | sed 's/^/         /'
    return 1
  fi
  say "  [OK   ] $dir/$script  | $(printf '%s\n' "$out" | tail -1)"
}

say '----------------------------------------------------------------'
say 'STEP 1-4  rung9: the medium and its pixel payload'
declare -A BEFORE=()
for rel in "${TRACKED_GENERATED[@]}"; do
  [[ -f $ROOT/$rel ]] && BEFORE[$rel]=$(sha256sum "$ROOT/$rel" | cut -d' ' -f1)
done
run_step rung9 bm903_mkimg.py      || true
run_step rung9 bm903_mkimg_px.py   || true
run_step rung9 bm903_pxcodec.py    || true
say '----------------------------------------------------------------'
say 'STEP 5-6  rung6: the ECC fork of the payload, and its 8 fixture media'
run_step rung6 bm602_pxcodec.py    || true
run_step rung6 bm602_mkimg.py      || true

say '----------------------------------------------------------------'
say 'LANDMARKS: the bytes every closed row downstream measures against'
for rel in rung9/bm903_stage1.bin rung9/bm903_stage2_px.bin \
           rung9/bm903_px_payload.bin rung9/bm903_medium_px.raw \
           rung6/bm602_px_payload.bin rung6/bm602_medium_px.raw; do
  check_landmark "$rel"
done

say '----------------------------------------------------------------'
say 'TRACKED: what the steps rewrote must be what was checked out'
moved=0
for rel in "${TRACKED_GENERATED[@]}"; do
  if [[ ! -f $ROOT/$rel ]]; then
    red "$rel is missing -- it is tracked, so no clean checkout should ever lack it"
    continue
  fi
  now=$(sha256sum "$ROOT/$rel" | cut -d' ' -f1)
  if [[ -n ${BEFORE[$rel]:-} && $now != "${BEFORE[$rel]}" ]]; then
    red "$rel moved under the regeneration: ${BEFORE[$rel]:0:16}... -> ${now:0:16}..."
    moved=$((moved + 1))
  fi
done
(( moved )) || say "  [OK   ] all ${#TRACKED_GENERATED[@]} generated-but-tracked files are byte-identical to the checkout"

say '================================================================'
if (( fail )); then
  say "PREREQ_STATUS=RED ($fail) -- do not run a row gate over this tree"
  exit 1
fi
say 'PREREQ_STATUS=GREEN'
say 'Now runnable, each from its own directory:'
say '  rung6:    bash run_bm602_e2e.sh'
say '  rung6_5:  bash run_bm653_e2e.sh   (needs rung6/fixtures/ for its regression leg)'
say '  rung9:    bash run_bm903_e2e.sh   (boots; its own statics are already done here)'
say '  rung8:    python3 bm802_fixture.py            (host-only selftest; reads rung9/bm903_medium_px.raw)'
