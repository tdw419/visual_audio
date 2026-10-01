#!/usr/bin/env python3
"""doc_ref_audit.py -- do the paths and line numbers this ladder's prose cites hold up?

Read-only. Run with no arguments it sweeps every `*.md` and `*.txt` under
tools/bare_metal_poc/ (ROADMAP, the receipts, the scoping notes and the
clean-tree evidence records); with file arguments, just those. The prose is
heavy -- several hundred backticked path tokens across eighty-odd files, the
exact count printed on every run rather than quoted here, because a number in
prose is a number that goes stale -- and every one of those tokens is
a promise a reviewer can knock on, which nothing tested until this landed. A
citation that points nowhere is the documentation equivalent of the conditional
guard this ladder already forbids: a check that quietly stops existing.

Four checks, one report:
  1. PATHS. Each backticked token that looks like a path is resolved; the
     failures print as UNRESOLVED and decide POINTER_STATUS.
  2. LINE NUMBERS. Both spellings -- `foo.sh:212` inline, and "foo.sh ... line
     212" within 200 characters -- are resolved to their file and range-checked,
     with the pointed-to text printed beside so a reader can judge whether that
     line is still the line the prose meant. Out of
     range prints as STALE and decides POINTER_STATUS.
  3. AMBIGUOUS BARE NAMES. A name that matches several files (`stage2.asm` is
     three here) satisfies check 1 and still leaves the reader to pick. This
     prints informationally and deliberately does NOT decide POINTER_STATUS --
     a citation to one of several real files is not a broken citation, and a
     tool that called it one would train people to ignore the list.
  4. OUTSIDE HEAD. A citation can resolve on this box and still be a promise no
     clean checkout can keep, because the file it names was never committed.
     Every path that resolves but is absent from `git ls-tree -r HEAD` is counted
     per target file, with the citing records beside it. Also informational, and for
     a sharper reason than check 3: the prose is not wrong here -- `git status`
     simply cannot show the gap, which is the same blind spot that hid the
     ignored population from TASK_BM001's landing plan. What this check settles
     is which untracked files are load-bearing for the ladder's own records, so
     "drop the scratch" and "cannot drop, three receipts cite it" stop being the
     same line in a decision.

What it does NOT claim:
  * UNRESOLVED is not the same as WRONG. Paths that live inside a guest image
    (`lib/libresolv-2.28.so`), fragments of a glob, intermediates a gate deletes
    on its own last line, and command snippets print here and are judged by the
    reader. Two real dead pointers it did find, both 2026-09-20: `bm653_consts.py`
    in BM653's own checkbox line, a stale claim rather than a missing file (the
    module was folded into `bm653_pxcodec.py`, which `RECEIPT_BM653.md` records
    as deviation (a)); and a pair of `../../` links in a clean-tree record that
    landed one directory above the ladder, so a reviewer following them hit
    nothing. The prose drifted; the tool caught it the same afternoon. Check 2
    has since flagged one citation of its own -- `BM650_SCOPING.md`'s bare
    stage2.asm:238, which lands on rung2's 108-line file and reads as out of
    range -- where the prose was right and only under-qualified: it meant
    rung5's. Both answers are in the design: qualify the prose, and print every
    candidate rather than arbitrating one.
  * It resolves a token against the citing file's own directory (so `../x/y.md`
    means what a reviewer would click), then tools/bare_metal_poc/, the repo
    root, and every directory under the ladder (prose says `evidence/x.txt`
    meaning rung6_5's), and resolves a bare basename against the whole project.
  * It refuses to read what is not UTF-8 text (two guest-memory dumps carry a
    `.txt` name) and says so on stdout, because an unstated skip is check 1
    becoming the thing it exists to catch.

  usage: python3 doc_ref_audit.py [--list-outside] [FILE ...]
         # default sweep: every *.md and *.txt here. --list-outside prints check
         # 4 as `count<TAB>path` for a machine reader and nothing else.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[0]          # tools/bare_metal_poc
REPO = BASE.parent.parent                           # project root

CAND = re.compile(r"`([^`\n]+)`")
PATHISH = re.compile(r"[A-Za-z0-9_.\-/]+\.[A-Za-z0-9]{1,5}$")
EXTS = {'.md', '.py', '.sh', '.asm', '.inc', '.json', '.txt', '.bin', '.raw',
        '.png', '.log', '.iso', '.gz', '.img', '.lst', '.csv', '.crc', '.norm',
        '.keep', '.so', '.ko'}


def looks_like_path(t: str) -> bool:
    if any(c in t for c in ' *$()|,;') or t.startswith(('http', 'mailto')):
        return False
    # An elision (`..._leg0.bin`), a fragment a sentence cut mid-name (`_B.txt`),
    # or a runtime path outside the repo (`/var/tmp/...`) is not a citation this
    # tree can honour, and counting them as failures hides the ones that are.
    if t.startswith(('...', '_', '/')) or t == Path(t).name and t.startswith('.'):
        return False
    return bool(PATHISH.fullmatch(t)) and (
        '/' in t or Path(t).suffix.lower() in EXTS)


def candidates(t, doc):
    """Every path this token could mean. Same roots as before, plus, for a bare
    name, every file of that name in the project.

    Returning all of them rather than the first is the point: `stage2.asm` is
    three files in this ladder, and a checker that quietly picks one gets to
    declare prose wrong on a coin flip.
    """
    hits = []
    for root in (doc.parent, BASE, REPO, *BASE.iterdir()):  # this file's dir, ladder-root, repo, any rung
        if root.is_dir():
            p = root / t
            if p.exists() and p not in hits:
                hits.append(p)
    if '/' not in t:
        hits += [p for p in by_name().get(t, ()) if p not in hits]
    return sorted(hits, key=str)


def resolves(t: str, doc: Path) -> bool:
    return bool(candidates(t, doc))


_TRACKED = None


def tracked():
    """Repo-relative paths HEAD carries, as one git call, cached.

    Check 4 needs the whole tree, so this is fetched lazily and once: the
    sweep costs a tenth of a second and the audit stays a seconds-scale tool.

    `ls-tree HEAD` and not `ls-files`: the question this check answers is what a
    clean checkout can honour, and the index is not that. Another lane's staged
    file is in `ls-files` and absent from HEAD, so the index version counted a
    promised file as delivered the moment somebody ran `git add` -- which on a
    box where three lanes commit at once is a claim about nobody's decision.
    """
    global _TRACKED
    if _TRACKED is None:
        out = subprocess.run(['git', 'ls-tree', '-r', '--name-only', '-z', 'HEAD'],
                             cwd=REPO, capture_output=True)
        if out.returncode:
            raise SystemExit(f'doc_ref_audit: `git ls-tree HEAD` failed: '
                             f'{out.stderr.decode().strip()}')
        _TRACKED = {s for s in out.stdout.decode().split('\0') if s}
    return _TRACKED


def rel_repo(p: Path):
    """Normalised repo-relative path, or None if the file is not in this repo.

    Normalisation is not cosmetic: candidates() can hand back
    `rung6_5/../reproduce_prereqs.sh`, and comparing that string against the
    index would call a tracked file untracked -- the false positive this whole
    check exists to avoid.
    """
    n = Path(os.path.normpath(str(p)))
    try:
        return str(n.relative_to(REPO))
    except ValueError:
        return None


_BY_NAME = None


def by_name():
    """Filename index for the whole project, built once and only if needed.

    Prose cites `.builder_queue/brief_bm903_guest_hermes.md` by full path in one
    row and by bare name in the next; both are live pointers, and the second one
    is outside the ladder, which is why a basename deserves the project-wide
    index. It is also what makes ambiguity visible instead of arbitrated.
    """
    global _BY_NAME
    if _BY_NAME is None:
        _BY_NAME = {}
        for p in REPO.rglob('*'):
            if '.git/' in str(p) or not p.is_file():
                continue
            _BY_NAME.setdefault(p.name, []).append(p)
    return _BY_NAME


FILEWORD = re.compile(r"[A-Za-z0-9_\-./]+\.[A-Za-z0-9]{1,5}")
INLINE = re.compile(r':(\d+)\b')
LINEPOS = re.compile(r'\blines?\s+(\d+)')
_LINES = {}


def nlines(p: Path) -> int:
    if p not in _LINES:
        try:
            _LINES[p] = len(p.read_text(errors='replace').splitlines())
        except OSError:
            _LINES[p] = -1
    return _LINES[p]


def at_line(p: Path, n: int) -> str:
    try:
        return p.read_text(errors='replace').splitlines()[n - 1].strip()
    except (IndexError, OSError):
        return ''


def line_pointers(doc: Path, text: str):
    """Every line-number citation in one document, and what each points at.

    Two spellings: `foo.sh:212` inline, and "foo.sh ... line 212" within WINDOW
    characters -- prose wraps, so this scans the whole text, not one line at a
    time. What it can decide mechanically is range: a line number past the end of
    *every* file the token could mean means the cited file was rewritten under
    the citation. Whether the line still says what the prose claims it says is a
    reader's call, so the pointed-to text prints beside it -- and for a bare name
    that several files answer to (`stage2.asm` is three here) the text prints for
    each of them, because picking one silently is how a checker gets to declare
    correct prose stale.
    """
    WINDOW = 200
    cands = []
    for m in FILEWORD.finditer(text):
        t = m.group(0).lstrip('/')
        if t.endswith('.'):
            t = t[:-1]
        ps = [p for p in candidates(t, doc) if p.is_file()]
        if ps:
            cands.append((m.start(), m.end(), t, ps))
    out = []
    seen = set()

    def record(pos, tok, ps, n):
        ln = text.count('\n', 0, pos) + 1
        if (ln, tok, n) in seen:
            return
        seen.add((ln, tok, n))
        ok = [p for p in ps if 0 < n <= nlines(p)]
        out.append((ln, tok, (ok or ps)[0], n,
                    [(p, at_line(p, n)) for p in ps], bool(ok)))

    for m in cands:                              # the `foo.sh:212` form
        hit = INLINE.match(text, m[1])
        if hit:
            record(hit.start(), m[2], m[3], int(hit.group(1)))
    for m in LINEPOS.finditer(text):             # the `... foo.sh ... line 212` form
        n = int(m.group(1))
        prior = [c for c in cands if c[1] <= m.start() and m.start() - c[1] <= WINDOW]
        if not prior:
            continue
        _, _, tok, ps = max(prior, key=lambda c: c[1])
        record(m.start(), tok, ps, n)
    return out


def main() -> int:
    args = sys.argv[1:]
    machine = '--list-outside' in args
    args = [a for a in args if a != '--list-outside']
    docs = ([Path(a).resolve() for a in args]
            or sorted(list(BASE.rglob('*.md')) + list(BASE.rglob('*.txt'))))
    checked = unresolved = 0
    clean_files = 0
    skipped = []
    pairs = []
    amb = {}
    outside = {}
    report = []
    for doc in docs:
        rel = doc.relative_to(BASE) if doc.is_relative_to(BASE) else doc
        try:
            text = doc.read_text()
        except UnicodeDecodeError as e:
            # A guest-memory dump with a .txt name is not prose. Skipping it is
            # only honest because the skip is printed, not swallowed.
            skipped.append(f'{rel} ({e.encoding} decode fails at byte {e.start})')
            continue
        except OSError as e:
            # Naming a document that is not there -- a mistyped path, a `--help`
            # -- is a skip the same kind as the one below it, not a traceback.
            skipped.append(f'{rel} ({type(e).__name__}: {e.strerror})')
            continue
        hits = []
        for i, line in enumerate(text.splitlines(), 1):
            for tok in CAND.findall(line):
                t = tok.strip().rstrip('.').rstrip(':')
                if not looks_like_path(t):
                    continue
                checked += 1
                cands = candidates(t, doc)
                if not cands:
                    hits.append((i, t))
                    continue
                if '/' not in t and len(by_name().get(t, ())) > 1:
                    amb.setdefault(t, [len(by_name()[t]), set()])[1].add(str(rel))
                # Check 4: does a clean checkout have what this cites? Every
                # candidate untracked means the promise holds only on this box.
                rels = {r for r in map(rel_repo, cands) if r}
                if rels and not (rels & tracked()):
                    # Keyed per file, not per token: a bare name with three
                    # untracked candidates is three promises, and collapsing them
                    # would understate what a clean checkout owes.
                    for r in sorted(rels):
                        ent = outside.setdefault(r, [0, set(), set()])
                        ent[0] += 1
                        ent[1].add(str(rel))
                        ent[2].add(t)
        if hits:
            unresolved += len(hits)
            report.append(f'{rel}: {len(hits)} unresolved')
            report.extend(f'  line {i}: {t}' for i, t in hits)
        else:
            clean_files += 1
        for rec in line_pointers(doc, text):
            pairs.append((rel, *rec))
    if machine:
        # For a consumer (bm001_landing_plan.sh buckets this by class). One line
        # per file outside HEAD: citation count, tab, repo-relative path.
        for r in sorted(outside, key=lambda p: (-outside[p][0], p)):
            print(f'{outside[r][0]}\t{r}')
        return 0
    for line in report:
        print(line)
    for s in skipped:
        print(f'  skipped, not text: {s}')
    if amb:
        print(f'\n{len(amb)} bare names that match more than one file '
              f'(informational: the citation holds, but a reader has to pick):')
        for t, (k, where) in sorted(amb.items(), key=lambda x: (-x[1][0], x[0])):
            print(f'  {t:32} {k} files  cited in {len(where)}: '
                  f'{", ".join(sorted(where)[:3])}'
                  + (f' (+{len(where) - 3} more)' if len(where) > 3 else ''))
    stale = 0
    if outside:
        files = sorted(outside, key=lambda r: (-outside[r][0], r))
        cites = sum(v[0] for v in outside.values())
        print(f'\n{cites} citation-to-file pairs across {len(docs) - len(skipped)} '
              f'prose files point at {len(outside)} files this commit does not '
              f'carry -- a clean checkout cannot honour them, and `git status` '
              f'never showed the gap:')
        print('  (a bare name that answers to several untracked files counts once '
              'per file, so `stage1_const.inc` is four entries, not one)')
        print('  cites  file  (cited by)')
        for r in files[:25]:
            n, by, toks = outside[r]
            print(f'  {n:5}  {r}')
            print(f'         by {", ".join(sorted(by)[:3])}'
                  + (f' (+{len(by) - 3} more)' if len(by) > 3 else '')
                  + (f'   [as {", ".join(sorted(toks)[:2])}'
                     f'{" +…" if len(toks) > 2 else ""}]'))
        if len(files) > 25:
            print(f'         ... and {len(files) - 25} more files, '
                  f'{sum(outside[r][0] for r in files[25:])} further citations')
    if pairs:
        print(f'\n{len(pairs)} line-number citations, with what each points at:')
        for rel, ln, tok, pick, n, bodies, ok in pairs:
            stale += not ok
            short = lambda p: (p.relative_to(REPO) if p.is_relative_to(REPO)
                               else p)
            flag = 'STALE    ' if not ok else 'in range '
            print(f"  {flag} {rel}:{ln} -> {short(pick)}:{n}  |  "
                  f"{at_line(pick, n)[:56]}")
            for p, body in bodies:
                if p != pick:
                    print(f'           and {short(p)}:{n}  |  {body[:56]}')
            if not ok:
                print(f'            [{len(bodies)} files answer to {tok} and '
                      'none of them has that line]')
    print(f'{len(docs) - len(skipped)} prose files ({clean_files} fully '
          f'resolving), {checked} backticked path tokens checked, '
          f'{len(pairs)} line citations ({stale} stale), {len(skipped)} skipped, '
          f'{len(outside)} cited files outside HEAD '
          f'({sum(v[0] for v in outside.values())} citations)')
    print(f'POINTER_STATUS={"REVIEW" if unresolved or stale else "CLEAN"} '
          f'({unresolved + stale})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
