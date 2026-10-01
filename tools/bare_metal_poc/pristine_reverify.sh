#!/usr/bin/env bash
# pristine_reverify.sh -- run the closed rows again, in a tree git handed us, at
# whatever HEAD is right now.
#
# Why. `rung6/evidence/cleanroom/pristine_rows_table.txt` is the record that a
# clean checkout reproduces the ladder -- but it names the commit it proved
# (c0ad33a1), and a record of a proof is not the proof. HEAD has moved since.
# This script re-pays the whole cost in one unattended leg so that the claim can
# be made about today's commit rather than about last week's, and it prints the
# wall time of every step so a reader can see the legs did not overlap: one
# booted rig at a time, which is how `run_bm653_e2e.sh` and the lanes do it.
#
# It writes ONLY under its scratch tree. The working copy is read for two things
# and touched for neither: `git archive HEAD` (so a dirty working tree cannot
# leak in -- that dirtiness is TASK_BM001's own finding) and rung7/core.gz, the
# one input no commit carries.
#
#   usage: cd tools/bare_metal_poc && setsid nohup bash pristine_reverify.sh \
#            [upper|lower] > /tmp/pristine_reverify.out 2>&1 &     # upper default
#          PRISTINE_DIR=/tmp/somewhere_else ...   # scratch root, default below
#
# Output: $T/logs/<leg>.log per leg, $T/logs/driver.log with a timestamped
# start/end/exit-code line each, and $T/logs/RUN_STATUS = GREEN only when every
# leg that ran exited 0, with the skip count on the same line. Every leg exits 0
# on its own success, including the ones that prove a check bites by catching a
# failure; see the note above the leg list.

set -u
set -o pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Two bare substitutions used to sit here: REPO and HEAD_SHA, each a `$(git ...)`
# that can fail without stopping anything. Measured 2026-09-20 in a `git archive`
# extraction of this directory -- the tree a ratifier is being shown: both
# substitutions printed `fatal: not a git repository` on stderr, the script
# carried on with both empty, printed the landmark line as `HEAD ` with nothing
# after it, and then died at whichever later check happened to fire first:
# "FATAL: scratch filesystem has 3651944 KB free", or, once rung7/core.gz was
# copied in, "FATAL: git archive | tar failed". Both name a cause that is not
# the cause, and the two git lines never reach driver.log, because they bypass
# `say`. Worse than a wrong cause is the case where the script is run somewhere
# that has some *other* git ancestor: REPO resolves, and the run reports on that
# repository's HEAD as if it were the ladder's. So the location is established
# before any check that could beat it, and a refusal says RUN_STATUS=RED rather
# than falling silent.
if ! REPO=$(cd "$ROOT" && git rev-parse --show-toplevel 2>/dev/null); then
  printf 'FATAL: %s has no git repository above it. This driver runs a tree it\n' "$ROOT" >&2
  printf 'archives from a named commit, and there is no commit to read. Nothing ran.\n' >&2
  printf 'RUN_STATUS=RED\n' >&2
  exit 3
fi
if [ "$ROOT" != "$REPO/tools/bare_metal_poc" ]; then
  printf 'FATAL: this script is at %s, not at %s/tools/bare_metal_poc.\n' "$ROOT" "$REPO" >&2
  printf 'The repository above it is not this ladder, so its HEAD is not the HEAD under\n' >&2
  printf 'test. Nothing ran. RUN_STATUS=RED\n' >&2
  exit 3
fi
CORE_SRC=$ROOT/rung7/core.gz
CORE_SHA=7f1e370dd4e489fd76c99f76ed9ddd79fd7e51f23af457b07071b3898bb8b5a2
if ! HEAD_SHA=$(cd "$REPO" && git rev-parse HEAD 2>/dev/null); then
  printf 'FATAL: %s is a git repository with no HEAD to archive (an empty history?).\n' "$REPO" >&2
  printf 'Nothing ran. RUN_STATUS=RED\n' >&2
  exit 3
fi
T=${PRISTINE_DIR:-/tmp/bm000_reverify_$(date +%Y-%m-%d_%H%M%S)}
L=$T/logs
S=$T/tools/bare_metal_poc

# Two trees, one script, because the guards belong to both: `upper` (default) is
# the five closed rows, which run from the commit plus one vendor blob and
# nothing else. `lower` is rungs 1-5, whose record (lower_rungs_pristine.txt) is
# a hand-run recipe at f14b5518; those rungs cannot all run from the commit
# alone -- that IS the finding -- so that mode proves the finding still bites and
# then runs each gate in a tree given the untracked sources it needs, copied in
# only after the bite check. The mode is printed in the driver's first line
# because a tree holding copied sources is not a tree holding only the commit.
MODE=${1:-upper}
if [ "$MODE" != upper ] && [ "$MODE" != lower ]; then
  printf '%s  FATAL: mode %s is neither upper nor lower; nothing was run.\n' \
    "$(date -u +%FT%TZ)" "$MODE" >&2
  exit 1
fi

say() { printf '%s  %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$L/driver.log"; }
abort() { mkdir -p "$L"; say "FATAL: $*"; say "RUN_STATUS=RED"; exit 1; }

if [ -d "$T" ] && [ -n "$(ls -A "$T")" ]; then
  abort "scratch root $T already holds something -- a pristine tree starts empty"
fi
mkdir -p "$L" || abort "cannot create $L"
# The first run of this script lost BM653 to `No space left on device` at 2.5 GB
# free on the filesystem holding the scratch tree, after 550 s of boots. A leg
# that dies of the box is not a leg that died of the ladder, so the floor is
# stated and checked instead of discovered an hour in.
AVAIL_KB=$(df -Pk "$T" | awk 'NR==2 {print $4}')
[ "$AVAIL_KB" -ge 4000000 ] || abort "scratch filesystem has ${AVAIL_KB} KB free; this leg wants 4 GB (point PRISTINE_DIR at a roomier device)"
say "HEAD $HEAD_SHA"
say "mode   $MODE"
say "scratch $T ($(( AVAIL_KB / 1024 )) MB free on its device)"

if [ "$MODE" = upper ]; then
  [ -f "$CORE_SRC" ] || abort "rung7/core.gz is not on this box: the one input no commit carries"
  [ "$(sha256sum "$CORE_SRC" | cut -d' ' -f1)" = "$CORE_SHA" ] || abort "rung7/core.gz sha256 is not the pinned one"
fi

# The archive is the whole point: nothing in the working tree that HEAD lacks
# may reach the run, so the tree is untarred from the named sha and nothing else
# -- "HEAD" would drift if another lane committed between the two archives below.
git -C "$REPO" archive "$HEAD_SHA" tools/bare_metal_poc | tar -x -C "$T" || abort "git archive | tar failed"
if [ "$MODE" = upper ]; then
  # rung7/ has no tracked file, so `git archive` does not create the directory at
  # all; the vendor blob goes where the closed rows look for it.
  mkdir -p "$S/rung7" && cp "$CORE_SRC" "$S/rung7/core.gz" || abort "could not place core.gz"
fi
# Not a count that could rot: the file every leg's first line depends on.
[ -f "$S/reproduce_prereqs.sh" ] || abort "the archive held no reproduce_prereqs.sh -- nothing was extracted"
say "tree built: $(find "$S" -type f | wc -l) files, all of them from $HEAD_SHA"

# Each leg: name, rung directory, command. Every one of them exits 0 on its own
# success, including the negative ones -- bm802_pin_bitest.py exists to prove the
# stage1 pin bites, and it prints `[BITES]` and exits 0 when the AssertionError
# fires, exiting 1 only if a wrong pin slips through. So no leg here needs an
# expected-sign column; the first draft of this script invented one for that file,
# inverted its verdict, and reported a green check as the run's only false RED.
LEGS=()
run_leg() {
  local name=$1 dir=$2
  shift 2
  local s=$(date +%s) rc=0
  say "START $name  ($dir: $*)"
  ( cd "$S/$dir" && "$@" ) > "$L/$name.log" 2>&1 || rc=$?
  local w=$(( $(date +%s) - s ))
  local verdict=PASS
  [ "$rc" != 0 ] && verdict=FAIL
  # A leg whose log holds the box running out of room says so, because the exit
  # code alone cannot tell a red gate from a full disk -- and the first run of
  # this script conflated them.
  grep -q 'No space left on device' "$L/$name.log" 2>/dev/null && verdict=ENV-FAIL
  say "END   $name  rc=$rc  ${w}s  $verdict"
  LEGS+=("$verdict  $name  rc=$rc  ${w}s")
  [ "$verdict" = PASS ] || FAILED=1
}
# A leg that did not run is said out loud and never recorded as a pass.
skip_leg() {
  say "SKIP  $1  -- $2"
  LEGS+=("SKIP  $1  -- $2")
  SKIPS=$((SKIPS + 1))
}
FAILED=0
SKIPS=0

if [ "$MODE" = upper ]; then
run_leg prereq         .          bash reproduce_prereqs.sh
run_leg bm903_pass1    rung9      bash run_bm903_e2e.sh
run_leg bm903_pass2    rung9      bash run_bm903_e2e.sh
run_leg bm902          rung9      bash run_bm902_diff.sh
run_leg bm802_fixture  rung8      python3 bm802_fixture.py
run_leg bm802_pin_bitest rung8    python3 bm802_pin_bitest.py
run_leg bm802_header   rung8      python3 bm802_header_fields.py
run_leg bm802_archive  rung8      python3 bm802_archive_local.py
run_leg bm802_preflight rung8     python3 run_bm802_sweep.py --limit=3 --recheck=2
run_leg bm602_pass1    rung6      bash run_bm602_e2e.sh
run_leg bm602_pass2    rung6      bash run_bm602_e2e.sh
run_leg bm651          rung6_5    bash run_bm651_e2e.sh
run_leg bm653          rung6_5    bash run_bm653_e2e.sh
else
# Rungs 1-5. The record this re-pays is lower_rungs_pristine.txt, made by hand at
# f14b5518: rungs 4 and 5 run from the commit, rung 1 has no gate in it, and
# rung 2's gate IS in the commit and dies on its first command there. That last
# one is a finding, not a failure, so it is proved the way bm802_pin_bitest.py
# proves its pin -- a leg whose own contract is to exit 0 when the thing bites.
# If the commit ever grows rung 2's sources, the leg goes RED and says the
# finding has changed, which is the correct outcome for a stale claim.
run_leg r2_from_commit rung2 \
  bash -c 'out=$(bash run_gate2.sh 2>&1)
           if grep -q "unable to open input file" <<<"$out"; then
             echo "[BITES] rung 2 from the commit alone dies at nasm, as recorded"
           else
             echo "NOT BITING -- the commit now carries what rung 2 needs, so this"
             echo "finding is stale and the record above it needs rewriting:"
             tail -20 <<<"$out"; exit 1
           fi'

# Now hand the tree the sources the commit does not carry -- named, so a landing
# that removes one is visible here rather than silently changing what was tested.
LOWER_ROOT='run_gate.sh boot.asm pxc1_boot_codec.py pxc1_nbd_plugin.py RECEIPT.md'
LOWER_R2='rung2/stage1.asm rung2/stage2.asm rung2/rung2_codec.py rung2/RECEIPT_RUNG2.md'
COPIED=()
for f in $LOWER_ROOT $LOWER_R2; do
  if [ -e "$ROOT/$f" ]; then
    mkdir -p "$S/$(dirname "$f")" && cp "$ROOT/$f" "$S/$f" && COPIED+=("$f")
  else
    say "NOTE  $f is not in the working tree either -- nothing to copy"
  fi
done
say "copied in ${#COPIED[@]} file(s) the commit does not carry: ${COPIED[*]}"

# Rung 1 is the only row here that runs a host server, over one unix socket path
# shared by every tree on this box, so it is not run alongside another.
if pgrep -x nbdkit >/dev/null 2>&1; then
  skip_leg r1_gate "another nbdkit is alive on this box; rung 1 needs the host socket to itself"
else
  run_leg r1_gate    .      bash run_gate.sh
fi
run_leg r2_gate      rung2  bash run_gate2.sh
run_leg r4_gate      rung4  bash run_gate4.sh
run_leg r5_gate      rung5  bash run_gate5.sh
fi

# Did the run leave the tree as it found it? Re-archiving the same commit and
# diffing is the only way to answer that without trusting the gates' own output:
# every file listed here is tracked, was written by a gate, and will show up as
# dirt in a reviewer's `git status` after a landing. It is reported, not failed on
# -- a gate that re-derives its own landed evidence is doing its job.
V=$T/verify
mkdir -p "$V"
if git -C "$REPO" archive "$HEAD_SHA" tools/bare_metal_poc | tar -x -C "$V"; then
  MOVED=$(diff -rq "$V/tools/bare_metal_poc" "$S" 2>/dev/null \
    | awk -v p="$V/tools/bare_metal_poc/" '$1 == "Files" { sub(p, "", $2); print $2 }')
  N=$(printf '%s\n' "$MOVED" | grep -c .)
  say "tracked files the run rewrote: $N"
  [ "$N" = 0 ] || printf '%s\n' "$MOVED" | sed 's|^|  |' | tee -a "$L/driver.log"
else
  # Not a zero: the measurement is missing.
  say "WARN: the re-archive failed, so tracked-file dirt was NOT measured."
fi

say '--- legs, in order:'
printf '%s\n' "${LEGS[@]}" | tee -a "$L/driver.log"
ST=GREEN; [ "$FAILED" = 0 ] || ST=RED
# A skip never lowers the status -- a leg that could not run here is the box's
# state, not the ladder's -- but it is on the status line, so GREEN cannot be
# read as "everything ran".
say "RUN_STATUS=$ST  mode $MODE  HEAD $HEAD_SHA  legs ${#LEGS[@]}  skips $SKIPS"
[ "$ST" = GREEN ] || say "  (see $L)"
printf '%s  %s  %s  skips=%s\n' "$(date -u +%FT%TZ)" "$ST" "$HEAD_SHA" "$SKIPS" \
  > "$L/RUN_STATUS"
say "logs: $L"
