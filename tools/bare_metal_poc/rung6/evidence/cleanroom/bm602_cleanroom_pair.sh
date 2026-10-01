#!/usr/bin/env bash
# Landed 2026-09-20 as run; W points at the lane, C at a scratch `git archive HEAD`
# tree under /tmp (that one is deleted -- re-run by pointing BM602_CLONE at a fresh
# archive that has had the ancestor recipe applied).
#
# BM602 clean-room pair: does rung6's gate reproduce in a tree that has never
# seen rung9's capture outputs? clone3 is a `git archive HEAD` checkout with the
# documented ancestor build steps already applied, and it holds
# rung9/bm903_px_regs_leg0.json (tracked) but NOT the two _leg0.bin dumps
# (ignored by the root *.bin rule) -- the exact clean-checkout condition.
#
# Run 1 uses the checkout's own identity stage (HEAD: no pin, no landed refs) and
# is EXPECTED to go RED on the missing reference, after paying for the boots.
# Run 2 uses the migrated stage (pinned copy landed at rung6/evidence/refs/) and
# must go GREEN. Same tree, same fixtures, one variable.
set -u
# The clean-room tree is an input, not something this script can create, so the
# name stays a default rather than going per-run: BM602_CLONE points at a fresh
# `git archive HEAD` tree with the ancestor recipe applied. Refusing up front is
# what matters — reaching a stale tree used to truncate that run's status record
# and then report rc=0 against it.
C=${BM602_CLONE:-/tmp/bm653_clone3_131457/tools/bare_metal_poc}
W=/home/jericho/projects/zion/projects/visual_audio/tools/bare_metal_poc
if [ ! -d "$C/rung6" ]; then
    echo "REFUSING: no clean-room tree at $C/rung6" >&2
    echo "  build one: git -C $W/../.. archive HEAD | tar -x -C <fresh-dir>" >&2
    echo "  apply the ancestor recipe, then re-run with" >&2
    echo "  BM602_CLONE=<fresh-dir>/tools/bare_metal_poc $0" >&2
    exit 1
fi
# This run's record. The old name lived inside the clone, so a second run
# truncated the first one's transcript; it is kept, not swept, because it is the
# output rather than scratch.
S=$(mktemp "${TMPDIR:-/tmp}/bm602_cleanroom_pair.XXXXXX")

cd "$C/rung6" || exit 1
echo "=== run 1: HEAD identity stage, no landed reference ===" >> "$S"
bash run_bm602_e2e.sh > logs/cleanroom_1.log 2>&1
echo "run1 rc=$?" >> "$S"
grep -E '^identity rc=|^GREEN |^RED |RUN_STATUS' logs/cleanroom_1.log >> "$S"

echo "=== migrate: pinned landed reference ===" >> "$S"
mkdir -p "$C/rung6/evidence/refs"
cp "$W/rung6/bm602_identity.py" "$C/rung6/bm602_identity.py"
cp "$W/rung6/evidence/refs/"* "$C/rung6/evidence/refs/"
cp "$W/rung6/.gitignore" "$C/rung6/.gitignore"
ls "$C/rung6/evidence/refs/" >> "$S"

echo "=== run 2: migrated identity stage ===" >> "$S"
bash run_bm602_e2e.sh > logs/cleanroom_2.log 2>&1
echo "run2 rc=$?" >> "$S"
grep -E '^identity rc=|^GREEN |^RED |RUN_STATUS' logs/cleanroom_2.log >> "$S"
echo "CLEANROOM_PAIR_DONE" >> "$S"
echo "record: $S"
