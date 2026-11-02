#!/usr/bin/env bash
# bm001_landing_plan.sh -- READ-ONLY view of what TASK_BM001 would land.
#
# TASK_BM001 is Jericho's ratification gate: which files under
# tools/bare_metal_poc/ enter git, which stay out, and which need a download
# step. Nothing here decides that -- it counts. Every category is derived from
# the current working tree, so the numbers cannot rot the way a prose count in
# ROADMAP.md does (the bullet that said "76 files" was written when the tree
# held a different set; this script's output is always now).
#
# Run it, read it, change nothing: it never touches the index, never adds a
# file, and writes no file.
#
#   usage: cd tools/bare_metal_poc && bash bm001_landing_plan.sh
#          bash bm001_landing_plan.sh --names BUCKET   # paths only, one per line
#          BUCKET: untracked | source | evidence | data | artifact | vendor |
#                  other | cited-untracked | cited-ignored | cited-elsewhere
#
# --names exists because the report above counts the ratification set but never
# spells it, and the only recipe that did was `git status -uall | grep '^??'` --
# which reads the index, so it agrees with this table only while three lanes
# happen to leave that index matching HEAD. The buckets are in the case below.

set -u
export LC_ALL=C          # every set operation below is a `comm`/`sort`: they must
                        # agree on what "sorted" means, and the repo's paths are
                        # ASCII, so pinning the locale costs nothing and rules out
                        # a comm that silently mis-aligns under a different collate.
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Fail before the first table, not after it. Measured: run from a `git archive`
# extraction of this very commit, the old version printed four `fatal: not a git
# repository` lines and then a report of all zeros -- which is exactly what a
# clean checkout "having nothing to land" would look like. The audit this script
# calls already exits 1 on the same condition; the script now matches it.
if ! REPO=$(cd "$ROOT" && git rev-parse --show-toplevel 2>/dev/null); then
  echo "fatal: $ROOT is not inside a git repository." >&2
  echo 'This report is HEAD compared against a worktree; with no repository it' >&2
  echo 'would measure nothing and print a zero for every count, and a zero that' >&2
  echo 'reads like a pass is the one output this ladder refuses.' >&2
  echo 'Run it from a checkout, or from tools/bare_metal_poc inside one.' >&2
  exit 3
fi
if [ "$ROOT" != "$REPO/tools/bare_metal_poc" ]; then
  echo "fatal: this script sits at $ROOT, not at $REPO/tools/bare_metal_poc." >&2
  echo 'Every path below is built from the repository root, so a relocated copy' >&2
  echo 'measures an empty set and calls it a tree with nothing outstanding.' >&2
  exit 3
fi

# `--names BUCKET` prints paths and nothing else, so a decision can be executed
# instead of transcribed. It is the same HEAD/worktree read the report uses; the
# only difference is that it names files rather than counting them.
NAMES=''
if [ "${1:-}" = '--names' ]; then
  NAMES=${2:-}
  if [ -z "$NAMES" ]; then echo 'usage: --names needs a bucket; see the case below.' >&2; exit 2; fi
  shift 2
fi
case "$NAMES" in
  ''|untracked|source|evidence|data|artifact|vendor|other|cited-untracked|cited-ignored|cited-elsewhere) ;;
  *) echo "usage: $0 [--names untracked|source|evidence|data|artifact|vendor|other|cited-untracked|cited-ignored|cited-elsewhere]" >&2; exit 2 ;;
esac

# Two populations, because `git status` shows only one of them. The ratification
# set is untracked-and-NOT-ignored, listed first; the ignored set is below it,
# swept explicitly, because a file .gitignore hides is a file no clean checkout
# will ever receive and no glance at `git status` will ever mention.
# The script's own dated snapshots are dropped from both, from the LIST below and
# from the tracked corpus the ignored section greps: a count that changes because
# someone wrote down the previous count is measuring the wrong thing.
#
# Neither set comes from the index, and that is a correctness rule, not a style
# one. Three lanes commit into this worktree at once, so `git ls-files` counts a
# file another lane has merely staged as delivered, and `git status -uall` drops
# it from the untracked pile. Measured with a copied index and one
# `git add -N tools/bare_metal_poc/rung2/stage1.asm` -- a file HEAD does not
# carry, and the reason rung 2's gate dies on its first command -- the index-fed
# version of this report said rung2 holds 3 files in git (HEAD: 2), called
# stage1.asm a tracked file differing from HEAD with `HEAD ? B` for its size,
# put the untracked total at 97 instead of 98, and filed the ladder's own file
# under "outside tools/bare_metal_poc/". So HEAD's tree and the bytes on this
# box are read directly, and the index appears only as the third thing it is: a
# staged-and-never-committed population, reported when non-empty.
HEAD_SET=$(cd "$REPO" && git ls-tree -r --name-only HEAD -- tools/bare_metal_poc)
# Everything under the ladder on this box, repo-relative.
ON_DISK=$(cd "$REPO" && find tools/bare_metal_poc -type f | sort)
# In the worktree but not in HEAD, then split by git's own ignore rules (read
# from the .gitignore files, not from the index).
NOT_IN_HEAD=$(comm -23 <(printf '%s\n' "$ON_DISK") <(printf '%s\n' "$HEAD_SET" | sort))
IGNORED_IN_WT=$(printf '%s\n' "$NOT_IN_HEAD" \
  | (cd "$REPO" && git check-ignore --no-index --stdin 2>/dev/null) | sort)
LIST=$(printf '%s\n' "$NOT_IN_HEAD" | comm -23 - <(printf '%s\n' "$IGNORED_IN_WT") \
        | grep -v -E '/bm001_landing_plan(_[0-9][0-9-]*)?\.txt$')
# The population neither of the two above is: staged by somebody, carried by no
# commit. Empty in a healthy tree and worth an explicit line either way. Set
# difference against HEAD rather than `git diff --cached`: an intent-to-add
# entry has no blob, so diff shows nothing for it -- measured, with a copied
# index and `git add -N`, where the diff version of this line stayed silent
# about the one file it exists to catch.
STAGED_ONLY=$(cd "$REPO" && git ls-files -- tools/bare_metal_poc | sort \
                | comm -23 - <(printf '%s\n' "$HEAD_SET" | sort))

# Third-party inputs git has never carried. Named, not patterned: they are the
# only entries here whose absence breaks a closed row, and each needs its own
# decision (vendor it in, or pin its sha and add a fetch step).
VENDOR_NAMES='core.gz TinyCore-current.iso'

classify() {                      # path -> class
  local f=$1 b=${1##*/} n
  for n in $VENDOR_NAMES; do
    [ "$b" = "$n" ] && { echo vendor; return; }
  done
  case "$f" in
    *.md|*.py|*.sh|*.asm|*.inc|*/.gitignore|.gitignore) echo source; return ;;
    *.png|*.raw|*.bin|*.img|*.lst|*.keep|*.log|*.out|*.norm|*.iso|*.gz|*.xz) echo artifact; return ;;
    */evidence/*) echo evidence; return ;;
    *.json|*.txt|*.csv) echo data; return ;;
  esac
  echo other
}

bytes_of() { [ -f "$REPO/$1" ] && stat -c%s "$REPO/$1" || echo 0; }

# The named form of every population the report counts. stdout is paths only --
# one per line, repository-relative -- so the list pipes straight into a command;
# the count and the byte weight go to stderr, where they can inform a decision
# without polluting the pipe. Read-only in this mode too: it lists, it never
# stages.
if [ -n "$NAMES" ]; then
  case "$NAMES" in
    untracked) OUT=$(printf '%s\n' "$LIST" | grep . | sort -u) ;;
    source|evidence|data|artifact|vendor|other)
      # A class row, spelled out. `--names source` is the "land the code" option
      # -- the one a ratification most often means, and the one the class table
      # above can only price, never name.
      OUT=$(while read -r f; do
              [ -n "$f" ] && [ "$(classify "$f")" = "$NAMES" ] && printf '%s\n' "$f"
            done <<< "$LIST" | sort -u) ;;
    *)
      # The three cited-outside-HEAD buckets, split the same way the report's
      # decision table splits them: in the ratification set, in the ignored set,
      # or outside the ladder where no commit that lands it can produce them.
      if ! CITED=$(cd "$REPO" && python3 "$ROOT/doc_ref_audit.py" --list-outside); then
        echo 'ERROR: the audit did not run, so this bucket was NOT measured.' >&2
        echo 'An empty list here would be a missing measurement, not a zero.' >&2
        exit 1
      fi
      declare -A S98=() SIG=()
      while read -r f; do [ -n "$f" ] && S98["$f"]=1; done <<< "$LIST"
      while read -r f; do [ -n "$f" ] && SIG["$f"]=1; done <<< "$IGNORED_IN_WT"
      OUT=$(while IFS=$'\t' read -r _ f; do
              [ -n "$f" ] || continue
              if   [ -n "${S98[$f]:-}" ] && [ "$NAMES" = cited-untracked ]; then printf '%s\n' "$f"
              elif [ -n "${SIG[$f]:-}" ] && [ "$NAMES" = cited-ignored ];   then printf '%s\n' "$f"
              elif [ -z "${S98[$f]:-}" ] && [ -z "${SIG[$f]:-}" ] && [ "$NAMES" = cited-elsewhere ]
              then printf '%s\n' "$f"; fi
            done <<< "$CITED" | sort -u)
      ;;
  esac
  B=0
  if [ -n "$OUT" ]; then
    printf '%s\n' "$OUT"
    B=$(printf '%s\n' "$OUT" | (cd "$REPO" && xargs -d '\n' stat -c%s | paste -sd+ | bc))
  fi
  printf '%s: %s paths, %s B\n' "$NAMES" "$(printf '%s\n' "$OUT" | grep -c .)" "$B" >&2
  exit 0
fi

bucket() {                         # repo-relative path -> the directory it sits in
  local rel=${1#tools/bare_metal_poc/} d
  d=${rel%%/*}
  [ "$d" = "$rel" ] && echo '(top)' || echo "$d"
}

printf '%-9s %5s %14s  %s\n' class files bytes 'what it is'
printf '%-9s %5s %14s  %s\n' ------- ----- ------------- '---------'
for c in source evidence data artifact vendor other; do
  n=0; tot=0
  while read -r f; do
    [ -n "$f" ] || continue
    [ "$(classify "$f")" = "$c" ] || continue
    n=$((n + 1)); tot=$((tot + $(bytes_of "$f")))
  done <<< "$LIST"
  case $c in
    source)   d='the tree the receipts cite: rung1-5 asm/code, scripts, docs' ;;
    evidence) d='landed records a reviewer checks the claims against' ;;
    data)     d='generated tables/JSON -- per row, is it a record or a product?' ;;
    artifact) d='build products and captures: every gate re-derives these' ;;
    vendor)   d='THIRD PARTY, outside git today: vendor in, or pin + fetch step' ;;
    other)    d='no rule matched -- worth a look before the ratification' ;;
  esac
  printf '%-9s %5s %14s  %s\n' "$c" "$n" "$tot" "$d"
done

# The class table answers "what kind of thing is this decision?" This one answers
# the sharper question a ratifier asks first: which parts of the ladder already
# exist in the commit, and which exist only on this box. A directory with 0 in
# git is not "mostly landed" -- a clean checkout has no such directory at all.
echo
echo 'Per directory: what HEAD already carries vs what only this box has'
printf '%-14s %7s %10s %6s  %s\n' dir in-git untracked of-src 'consequence for a clean checkout'
declare -A TR UN SRC
MISS=0
while read -r f; do
  [ -n "$f" ] || continue
  d=$(bucket "$f")
  if [ -f "$REPO/$f" ]; then
    TR[$d]=$(( ${TR[$d]:-0} + 1 ))
  else
    MISS=$(( MISS + 1 )); printf '  [deleted] %s\n' "${f#tools/bare_metal_poc/}"
  fi
done < <(printf '%s\n' "$HEAD_SET")
while read -r f; do
  [ -n "$f" ] || continue
  d=$(bucket "$f"); UN[$d]=$(( ${UN[$d]:-0} + 1 ))
  [ "$(classify "$f")" = source ] && SRC[$d]=$(( ${SRC[$d]:-0} + 1 ))
done <<< "$LIST"
tsrc=0
# Sorted under the pinned locale, which puts `(top)` first by ASCII; it is the
# last row of this table by convention, so it is appended rather than sorted in.
DIRS=$(printf '%s\n' "${!TR[@]}" "${!UN[@]}" | grep -v -x '(top)' | sort -u)
[ -n "${TR[(top)]:-}${UN[(top)]:-}" ] && DIRS=$(printf '%s\n(top)\n' "$DIRS")
for d in $DIRS; do
  t=${TR[$d]:-0}; u=${UN[$d]:-0}; s=${SRC[$d]:-0}
  tsrc=$(( tsrc + s ))
  if   (( t == 0 && u > 0 )); then note='WHOLLY OUTSIDE GIT -- `git archive` does not create it'
  elif (( u == 0 )); then note='landed; nothing here waits on the ratification'
  else note="$t of $(( t + u )) in git"
  fi
  printf '%-14s %7s %10s %6s  %s\n' "$d" "$t" "$u" "$s" "$note"
done
echo "                                                       (of-src total: $tsrc)"
# The mirror image of the untracked set: HEAD carrying a file this box has
# thrown away. Neither side shows up in the other's listing.
if (( MISS )); then
  echo "  ^ $MISS file(s) tracked in HEAD but absent from this box (listed above)."
  echo "    Those are deletions waiting to be either committed or restored."
else
  echo 'Every file HEAD tracks under the ladder is present on this box.'
fi

# A third state, and the one neither listing above can show: a tracked file
# whose bytes on this box differ from HEAD. This is not an unfinished edit --
# a GREEN gate can cause it. rung 4's gate ends by rebuilding the 64 KB medium
# as "the standing artifact set" while HEAD tracks the 256 KB one, so every
# passing run of run_gate4.sh leaves rung4_medium.png modified, and a receipt
# that stamps its own date does the same to itself. Either way the consequence
# is the same for a ratifier: `git status` is not a signal of work in progress
# here, so "clean tree" cannot be the test that a landing is finished. This
# tool's own dated snapshots stay out of the listing for the reason they stay out
# of the counts: a record being written is not a finding, and leaving it in would
# make every snapshot incapable of reproducing the run that produced it.
MOD=$(cd "$REPO" && git diff --name-only HEAD -- tools/bare_metal_poc \
        | sort | comm -12 - <(printf '%s\n' "$HEAD_SET" | sort) \
        | grep -v -E '(^|/)bm001_landing_plan(_[0-9][0-9-]*)?\.txt$')
if [ -z "$MOD" ]; then
  echo 'No tracked file under the ladder differs from HEAD: this tree is clean.'
else
  printf 'Tracked files whose bytes here differ from HEAD (%s):\n' "$(printf '%s\n' "$MOD" | grep -c .)"
  while read -r f; do
    [ -n "$f" ] || continue
    printf '  %-46s here %s B, HEAD %s B\n' "${f#tools/bare_metal_poc/}" \
      "$(stat -c%s "$REPO/$f" 2>/dev/null || echo '?')" \
      "$(cd "$REPO" && git cat-file -s "HEAD:$f" 2>/dev/null || echo '?')"
  done <<< "$MOD"
fi

# The fourth state, and the one this box is most likely to be in: a file in the
# index that no commit carries. Somebody else's `git add`, three lanes sharing
# one index. It is not the ratification's and not the ignored pile's, and every
# count above deliberately refuses to see it, so it gets its own line -- with the
# warning that the numbers here are unaffected precisely because none of them
# reads the index.
echo
if [ -z "$STAGED_ONLY" ]; then
  echo 'Nothing is staged-and-uncommitted under the ladder: the index and HEAD'
  echo 'agree, so no reader has to wonder which of these numbers came from which.'
else
  printf 'Staged in this box'"'"'s index, carried by NO commit (%s):\n' \
    "$(printf '%s\n' "$STAGED_ONLY" | grep -c .)"
  printf '%s\n' "$STAGED_ONLY" | sed 's|^|  |'
  echo '  Another lane is mid-landing. Nothing counted above moved -- this report'
  echo '  reads HEAD and the worktree, never the index, and before that was fixed'
  echo '  one `git add -N` of a single untracked .asm moved five of its numbers:'
  echo '  the directory in-git count, the source bucket, the untracked total, the'
  echo '  decision split, and a phantom "tracked file differing from HEAD".'
fi

echo
echo 'Gate entry points this commit cannot run -- untracked files named run_* or'
echo '*probe*. A reviewer who lands nothing cannot re-derive those rows at all.'
gn=0
while read -r f; do
  [ -n "$f" ] || continue
  case ${f##*/} in
    run_*|*probe*.sh|*probe*.py)
      printf '  %s\n' "${f#tools/bare_metal_poc/}"; gn=$((gn + 1)) ;;
  esac
done <<< "$LIST"
(( gn )) || echo '  none -- every gate script the ladder names is in the commit'

echo
echo 'Biggest five untracked files (the byte-weight of the decision):'
while read -r f; do
  [ -n "$f" ] || continue
  printf '%12s  %s\n' "$(bytes_of "$f")" "${f#tools/bare_metal_poc/}"
done <<< "$LIST" | sort -rn | head -5

echo
echo 'Vendor inputs (by existence, not by git status -- one of them is IGNORED,'
echo ' so `git status` never shows it and a clean checkout silently lacks it):'
for n in $VENDOR_NAMES; do
  hit=$(find "$ROOT" -maxdepth 2 -name "$n" 2>/dev/null | head -1)
  [ -n "$hit" ] || { printf '  %-26s absent from this box\n' "$n"; continue; }
  rel=${hit#$ROOT/}
  ign=$(cd "$REPO" && git check-ignore -v "$rel" 2>/dev/null | cut -f1 || true)
  if [ -n "$ign" ]; then
    printf '  %-26s %11s B  sha256 %s...  IGNORED by %s\n' "$rel" \
      "$(stat -c%s "$hit")" "$(sha256sum "$hit" | cut -c1-16)" "$ign"
  else
    printf '  %-26s %11s B  sha256 %s...  untracked, not ignored\n' "$rel" \
      "$(stat -c%s "$hit")" "$(sha256sum "$hit" | cut -c1-16)"
  fi
done

# Everything the listings above structurally cannot show. `git status` omits
# ignored paths by definition, so the "untracked" count is only the half that
# asks to be ratified; this is the other half, which a clean checkout never
# receives and no ordinary glance at the tree sees.
echo
echo 'The ignored population -- what `git status` cannot show at all. Every count'
echo 'above is the untracked-and-NOT-ignored set; these are the files .gitignore'
echo 'hides from it, which is how the .iso above stopped being a curiosity and'
echo 'became the visible tip of a much larger set:'
IGN=$(printf '%s\n' "$IGNORED_IN_WT")
if [ -z "$IGN" ]; then
  echo '  none -- nothing under the ladder is ignored on this box'
else
  # Which of them does the tree itself know about? A basename that appears in
  # any tracked text file is cited by a gate or a receipt; one that appears
  # nowhere is scratch by the tree's own reckoning. This tool's own snapshots are
  # dropped from the corpus for the same reason they are dropped from the LIST
  # above: the run whose numbers get written down records those largest-five
  # names, so leaving the snapshots in lets the next run re-classify the
  # previous run's listing as citations and move the split it is reporting.
  names=()
  while read -r f; do [ -n "$f" ] && names+=(-e "${f##*/}"); done <<< "$IGN"
  hits=$(printf '%s\n' "$HEAD_SET" \
           | grep -v -E '(^|/)bm001_landing_plan(_[0-9][0-9-]*)?\.txt$' \
           | (cd "$REPO" && xargs -d '\n' grep -Iho -F "${names[@]}" 2>/dev/null) | sort -u)
  declare -A HIT=()
  while read -r n; do [ -n "$n" ] && HIT["$n"]=1; done <<< "$hits"
  icount=0; ibytes=0; ncount=0; nbytes=0; ucount=0; ubytes=0
  while read -r sz f; do
    [ -n "$f" ] || continue
    icount=$((icount + 1)); ibytes=$((ibytes + sz))
    if [ -n "${HIT[${f##*/}]:-}" ]; then
      ncount=$((ncount + 1)); nbytes=$((nbytes + sz))
    else
      ucount=$((ucount + 1)); ubytes=$((ubytes + sz))
    fi
  done < <(cd "$REPO" && printf '%s\n' "$IGN" | xargs -d '\n' stat -c '%s %n' 2>/dev/null)
  printf '  %s files, %s B ignored under the ladder\n' "$icount" "$ibytes"
  printf '    a tracked file spells its name:   %s files, %s B\n' "$ncount" "$nbytes"
  printf '    no tracked file spells its name:  %s files, %s B\n' "$ucount" "$ubytes"
  echo '    Spelled-out is not produced: a script that composes a filename from a'
  echo '    variable hides its own outputs from this test, so the second line is a'
  echo '    cleanup candidate list and not a verdict. Every closed gate re-derives'
  echo '    its own products either way, which is what a pristine tree is for.'
  echo
  echo '  The rules that hide them (count, then .gitignore source:pattern):'
  (cd "$REPO" && printf '%s\n' "$IGN" | xargs -d '\n' git check-ignore -v 2>/dev/null \
      | cut -f1 | sort | uniq -c | sort -rn | head -8 | sed 's/^/    /')
  echo '  Largest, and whether any tracked file spells the name:'
  while read -r sz f; do
    [ -n "$f" ] || continue
    if [ -n "${HIT[${f##*/}]:-}" ]; then k='spelled'; else k='unspelled'; fi
    printf '    %12s B  %-10s %s\n' "$sz" "$k" "${f#tools/bare_metal_poc/}"
  done < <(cd "$REPO" && printf '%s\n' "$IGN" | xargs -d '\n' stat -c '%s %n' 2>/dev/null \
             | sort -rn | head -5)
fi

# The intersection neither tool can reach alone: doc_ref_audit.py check 4 knows
# which files the ladder's prose cites and HEAD does not carry; this script knows
# what class each of them is. Together they answer the question a ratifier asks
# of the untracked pile -- not "how big is it" but "which of these do the records
# promise", because a file seven receipts name is not scratch no matter what its
# extension says.
#
# No `if the audit exists` guard, and no silent zero: if it cannot run this
# script stops with a non-zero status rather than printing an empty table that
# reads as "nothing is promised outside the commit". A blank that looks like a
# pass is the one output this ladder has rejected everywhere else.
AUD=$ROOT/doc_ref_audit.py
echo
echo 'Cited by the prose, absent from the commit (doc_ref_audit.py check 4,'
echo 'bucketed by the classes above). Every file here is a promise a clean'
echo 'checkout cannot keep AND a name some record spells, so "drop it as scratch"'
echo 'is not available for these:'
if ! CITED=$(cd "$REPO" && python3 "$AUD" --list-outside); then
  echo 'ERROR: the audit did not run, so the intersection below was NOT measured.'
  echo 'This is a missing measurement, not a zero. Fix the audit and re-run.'
  exit 1
fi
declare -A CF=() CB=() CC=()
tfiles=0; tcites=0; tbytes=0
while IFS=$'\t' read -r n f; do
  [ -n "$f" ] || continue
  c=$(classify "$f"); sz=$(bytes_of "$f")
  CF[$c]=$(( ${CF[$c]:-0} + 1 )); CC[$c]=$(( ${CC[$c]:-0} + n )); CB[$c]=$(( ${CB[$c]:-0} + sz ))
  tfiles=$(( tfiles + 1 )); tcites=$(( tcites + n )); tbytes=$(( tbytes + sz ))
done <<< "$CITED"
# The cut a class table cannot make: which of these can TASK_BM001 deliver at
# all? A promised file may be in the ratification's own scope, in the ignored set
# the section above just measured, or outside tools/bare_metal_poc/ entirely --
# and a commit that lands the ladder cannot produce the third kind no matter what
# it decides about the first two.
declare -A IN98=() INIG=()
while read -r f; do [ -n "$f" ] && IN98["$f"]=1; done <<< "$LIST"
while read -r f; do [ -n "$f" ] && INIG["$f"]=1; done <<< "$IGN"
n_scope=0; n_ignored=0; n_elsewhere=0; elsewhere=()
b_scope=0; b_ignored=0; b_elsewhere=0
while IFS=$'\t' read -r cnt f; do
  [ -n "$f" ] || continue
  sz=$(bytes_of "$f")
  if [ -n "${IN98[$f]:-}" ]; then n_scope=$((n_scope + 1)); b_scope=$((b_scope + sz))
  elif [ -n "${INIG[$f]:-}" ]; then n_ignored=$((n_ignored + 1)); b_ignored=$((b_ignored + sz))
  else n_elsewhere=$((n_elsewhere + 1)); b_elsewhere=$((b_elsewhere + sz)); elsewhere+=("$f"); fi
done <<< "$CITED"
n_list=$(printf '%s\n' "$LIST" | grep -c .)

if [ "$tfiles" = 0 ]; then
  echo '  none -- no citation in the swept prose points at a file the commit lacks.'
  echo '  That is a claim about the prose, and not the empty output of a check that'
  echo '  failed to run, which is the case the ERROR branch above exists to catch.'
else
  printf '%-9s %6s %6s %14s  %s\n' class files cites bytes 'what it means for the promise'
  for c in source evidence data artifact vendor other; do
    [ -n "${CF[$c]:-}" ] || continue
    case $c in
      source)   note='code or prose nobody can read from a clean checkout' ;;
      evidence) note='a landed record whose own evidence file is missing' ;;
      data)     note='a table or JSON a receipt points at' ;;
      artifact) note='a build product -- regenerable, if the build is in git' ;;
      vendor)   note='third-party bytes; needs a pin and a fetch step' ;;
      *)        note='no rule; look at it' ;;
    esac
    printf '%-9s %6s %6s %14s  %s\n' "$c" "${CF[$c]}" "${CC[$c]}" "${CB[$c]}" "$note"
  done
  printf '%-9s %6s %6s %14s\n' TOTAL "$tfiles" "$tcites" "$tbytes"
  echo
  echo '  Which decision each of them belongs to, because the three are not one backlog:'
  printf '    %6s  among the %s files TASK_BM001 is asked about: land these and the promise holds  (%s B)\n' "$n_scope" "$n_list" "$b_scope"
  printf '    %6s  in the ignored set: a different decision -- un-ignore, or pin and fetch  (%s B)\n' "$n_ignored" "$b_ignored"
  printf '    %6s  outside tools/bare_metal_poc/: no commit that lands the ladder produces these  (%s B)\n' "$n_elsewhere" "$b_elsewhere"
  for f in "${elsewhere[@]:-}"; do
    [ -n "$f" ] && printf '              %s\n' "$f"
  done
  echo '  These three lines are counts and weights, not names. To act on one of'
  echo '  them without re-deriving it from `git status`: --names BUCKET prints any'
  echo '  bucket here, or any class row above, or `untracked`, as one path per'
  echo '  line on stdout with its size on stderr.'
fi
echo '  Counts are per file, cites per citation; a bare name that answers to'
echo '  several files counts once for each, which is what an under-qualified'
echo '  citation costs. A handful of these sit outside the ladder entirely'
echo '  (records belonging to a different lane), and they are listed because'
echo '  the audit sweeps what this ladder cites, not who owns the file.'

echo
echo 'No rule matched these -- an extension the classifier does not know:'
while read -r f; do
  [ -n "$f" ] || continue
  [ "$(classify "$f")" = other ] || continue
  printf '  %12s  %s\n' "$(bytes_of "$f")" "${f#tools/bare_metal_poc/}"
done <<< "$LIST"

echo
echo "Total untracked-and-not-ignored: $(printf '%s\n' "$LIST" | grep -c . ) files"
echo 'Read-only run: nothing staged, no file written. The decision is Jericho'
echo '(ROADMAP TASK_BM001); the check that a landed tree still works is one'
echo 'command -- bash pristine_reverify.sh upper (13 legs: the closed rows, the'
echo 'commit plus one vendor blob) or ... lower (5 legs: rungs 1-5, which need the'
echo 'untracked sources copied in -- the run proves that first). Both modes print'
echo 'the tracked files their own gates rewrote. What they gave is in'
echo 'rung6/evidence/cleanroom/: pristine_reverify_at_1de7ee86.txt and'
echo 'lower_rungs_pristine_at_88562ec0.txt.'
