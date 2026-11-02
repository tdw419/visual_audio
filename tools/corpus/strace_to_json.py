#!/usr/bin/env python3
"""strace_to_json.py — convert strace -f -ttt -T -s 256 output to corpus JSON.

Contract: docs/SYSCALL_CORPUS_SCHEMA.md (va-syscall-corpus/1).
Stdlib only. Lossless at capture time: args stay raw strings; consumers
decode. Unfinished/resumed pairs are excluded and COUNTED, never silent.

Usage: strace_to_json.py trace.log trace.json
"""
import json
import re
import sys

SCHEMA = "va-syscall-corpus/1"

# group(1)=pid  group(2)=ts  group(3)=body   (body ends before '= <ret>')
LINE_RE = re.compile(r"^(\d+)\s+(\d+\.\d+)\s+(.*)$")
# group(1)=name+args  group(2)=ret ('?' | 0xhex | -int | int)  + tail
# hex branch FIRST: '-?\d+' would otherwise eat the leading '0' of '0x...'
CALL_RE = re.compile(r"^(.*?)\s*=\s*(\?|0x[0-9a-f]+|-?\d+)(.*)$")
PATH_RE = re.compile(r"\"((?:[^\"\\]|\\.)*)\"")  # first quoted string, \" aware
# tail = everything after '= <ret>' — on failure it starts ' EACCES (...)'
ERRNO_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]+)\s")

NAME_RE = re.compile(r"^([a-zA-Z0-9_]+)\((.*)$", re.S)


def split_args(argstr):
    """Split 'a, b, c' on top-level commas (parens/brackets/quotes aware)."""
    args, depth, cur, i = [], 0, "", 0
    in_q = False
    while i < len(argstr):
        c = argstr[i]
        if in_q:
            if c == "\\":
                cur += argstr[i:i + 2]
                i += 2
                continue
            if c == '"':
                in_q = False
        elif c == '"':
            in_q = True
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            args.append(cur.strip())
            cur = ""
            i += 1
            continue
        cur += c
        i += 1
    if cur.strip():
        args.append(cur.strip())
    return args


def parse_path(args_raw):
    for a in args_raw:
        if a.startswith('"'):
            m = PATH_RE.match(a)
            if m:
                return m.group(1)
    return None


def convert(lines):
    calls, t0, skipped, pending = [], None, 0, {}
    for ln in lines:
        m = LINE_RE.match(ln)
        if not m:
            continue
        pid, ts, body = int(m.group(1)), float(m.group(2)), m.group(3)
        if "<unfinished ...>" in body:
            pm = CALL_RE.match(body)
            if pm:
                nm = NAME_RE.match(pm.group(1))
                if nm:
                    pending[pid] = (ts, nm.group(1))
            skipped += 1
            continue
        if "resumed" in body:
            # '<... openat resumed>:unfinished details> = ret' — pair already
            # counted when the unfinished half was seen.
            skipped += 1
            continue
        cm = CALL_RE.match(body)
        if not cm:
            continue
        head, ret_s, tail = cm.group(1), cm.group(2), cm.group(3)
        nm = NAME_RE.match(head)
        if not nm:
            continue
        if t0 is None:
            t0 = ts
        dur = None
        dm = re.search(r"<([\d.]+)>$", tail)
        if dm:
            dur = float(dm.group(1))
        errno = None
        em = ERRNO_RE.search(tail)
        if em:
            errno = em.group(1)
        args_raw = split_args(nm.group(2)) if nm.group(2) else []
        calls.append({
            "n": len(calls), "pid": pid,
            "ts_rel_us": round((ts - t0) * 1e6, 3),
            "duration_us": dur,
            "name": nm.group(1),
            "args_raw": args_raw,
            "path": parse_path(args_raw),
            "ret": int(ret_s) if re.fullmatch(r"-?\d+", ret_s) else None,
            "ret_raw": ret_s,
            "errno": errno,
        })
    return calls, skipped


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    with open(sys.argv[1], "r", errors="replace") as f:
        lines = f.read().splitlines()
    calls, skipped = convert(lines)
    out = {"schema": SCHEMA, "source": sys.argv[1].split("/")[-1],
           "counts": {"total": len(calls) + skipped,
                      "converted": len(calls),
                      "skipped_unfinished": skipped},
           "syscalls": calls}
    with open(sys.argv[2], "w") as f:
        json.dump(out, f, indent=1)
    print(f"{sys.argv[2]}: {out['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
