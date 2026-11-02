#!/usr/bin/env python3
"""geos_mailbox.py — audit CLI for the agent maildrop.

Read side of the inter-agent channel (tools/geos_maildrop.py). Lists
messages by recipient/author with their write identity and tamper status.

Usage:
    python3 tools/geos_mailbox.py list --to claude
    python3 tools/geos_mailbox.py list --from hermes --all
    python3 tools/geos_mailbox.py post --from hermes --to glyphgpt \
        --kind receipt --text "..."
    python3 tools/geos_mailbox.py verify --to all

Exit codes: 0 clean, 1 tamper detected, 2 usage/refused.
"""

import argparse
import hashlib
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from tools.geos_maildrop import Maildrop, verify_all  # noqa: E402

_DEFAULT_DROP = _REPO / ".geos" / "maildrop"
_DEFAULT_REG = _REPO / ".geos" / "spine_index.jsonl"


def _drop(args) -> Maildrop:
    return Maildrop(
        publish_dir=Path(args.drop_dir),
        registry_path=Path(args.registry),
        ack_file=Path(args.ack) if args.ack else None,
    )


def _read_all(drop: Maildrop, sender=None):
    """Every message regardless of recipient, with sender filter."""
    out = []
    for p in sorted(drop.content_dir.glob("*.md")):
        meta = drop._meta_for(p)
        if meta is None:
            continue
        if sender is not None and meta.get("sender") != sender:
            continue
        body = p.read_bytes()
        verified = hashlib.sha256(body).hexdigest() == meta.get("sha256")
        out.append({
            "sender": meta.get("sender"),
            "recipient": meta.get("recipient"),
            "kind": meta.get("kind"),
            "text": body.decode(errors="replace").split("\n\n", 1)[-1].rstrip("\n"),
            "content_path": str(p),
            "sha256": meta.get("sha256"),
            "verified": verified,
            "write_id": meta.get("write_id"),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(prog="geos_mailbox")
    ap.add_argument("--drop-dir", default=str(_DEFAULT_DROP))
    ap.add_argument("--registry", default=str(_DEFAULT_REG))
    ap.add_argument("--ack", default=None,
                    help="ack file for posting (default: repo .geos_emit_ack)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list messages")
    p_list.add_argument("--to", default=None, dest="to")
    p_list.add_argument("--from", default=None, dest="from_")
    p_list.add_argument("--all", action="store_true",
                        help="ignore recipient filter")

    p_post = sub.add_parser("post", help="post a message")
    p_post.add_argument("--from", required=True, dest="from_")
    p_post.add_argument("--to", required=True, dest="to")
    p_post.add_argument("--kind", required=True,
                        choices=("ruling", "claim", "receipt", "handoff",
                                 "brief", "status"))
    p_post.add_argument("--text", required=True)

    p_verify = sub.add_parser("verify", help="verify hashes for a recipient")
    p_verify.add_argument("--to", required=True, dest="to")

    args = ap.parse_args()
    drop = _drop(args)

    if args.cmd == "list":
        msgs = (_read_all(drop, args.from_) if args.all
                else drop.read(recipient=args.to or "all", sender=args.from_))
        if not msgs:
            print("(no messages)")
            return 0
        for m in msgs:
            flag = "OK " if m["verified"] else "TAMPER"
            print(f"[{flag}] w{m['write_id']} {m['sender']} -> "
                  f"{m['recipient']} ({m['kind']}): {m['text'][:70]}")
            print(f"       {m['content_path']}")
        return 0 if all(m["verified"] for m in msgs) else 1

    if args.cmd == "post":
        from tools.geos_maildrop import MaildropRefused
        try:
            r = drop.post(sender=args.from_, recipient=args.to,
                          kind=args.kind, text=args.text)
        except MaildropRefused as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        print(f"posted: write_id={r['write_id']} seq={r['seq']} "
              f"word={r['word']:#x} sha256={r['sha256'][:12]}…")
        print(f"  {r['content_path']}")
        return 0

    if args.cmd == "verify":
        rc = verify_all(drop, recipient=args.to)
        print("all verified" if rc == 0 else "TAMPER DETECTED")
        return rc

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
