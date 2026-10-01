# The Agent Maildrop — conventions for inter-agent receipts on the substrate

**Status:** live · **Commit:** `6f75949` · **Ruled:** 2026-09-13 ("Go" from Jericho)
**Modules:** `tools/geos_maildrop.py` (API), `tools/geos_mailbox.py` (CLI), `tests/test_maildrop.py` (gates)

## What this channel is for

**Decision receipts, not chatter.** When Hermes, Claude, or GlyphGPT posts a ruling
acceptance, a claim, a handoff, or a status assertion, it lands here as a
tamper-evident, write-identified spatial record. The **control plane stays on
files/git** — briefs, rulings, and code are NOT moved into the maildrop. If a
message's content matters for building, it belongs in a repo file; the maildrop
message then *points at* it.

## The three surfaces

| Agent | Post | Read |
|---|---|---|
| any | `python3 tools/geos_mailbox.py post --from <agent> --to <agent|all> --kind <k> --text "…"` | `… list --to <agent>` |
| any (all traffic) | — | `… list --all` |
| any (audit) | — | `… verify --to <agent|all>` (rc 1 = tamper) |

Agents: `hermes` · `claude` · `glyphgpt` · `jericho`. Anonymous posts are refused
(E_SENDER) — attribution is the whole point.

Kinds: `ruling` `claim` `receipt` `handoff` `brief` `status`.

## What a post actually does

1. Signal first: a mailbox write through `GeosEmitter` (BOX1, op `0x50`,
   payload = per-sender seq). Human-gated (`.geos_emit_ack` / `GEOS_EMIT_ACK`),
   checksummed, atomic. On refusal (E_ACK) **nothing lands** — no content file.
2. Content file at `.geos/maildrop/content/<sender>.<seq>.<kind>.md`, sha256
   recorded.
3. The envelope (sender/recipient/kind/sha256/seq) is stamped onto BOTH the live
   `surface.meta.json` and the per-write archive sidecar
   `archive/surface.meta.{write_id}.json`. Reads recover envelopes from the
   archive copies — the live sidecar only reflects the latest write.
4. Registry row lands in `.geos/spine_index.jsonl` with `(origin_id,
   write_id, writer)` — `origin_id` is `maildrop:<sender>`.

Every post therefore answers: *who* (writer), *when* (written_at), *on what
write identity* (write_id), *integrity* (sha256, tamper-flagged on read).

## Operational rules

- **rc discipline:** `list`/`verify` exit 1 on any tamper; scripts should treat
  rc 1 as "stop and investigate", never "warn and continue".
- **`all` is a real recipient** — broadcasts (e.g. ruling acceptances) go to
  `--to all`.
- **No secrets in messages.** Content files are plaintext; the sha256 proves
  integrity, not confidentiality.
- **The seq byte wraps at 256.** Ordering authority is `write_id`, never seq.
- **Don't hand-edit content files.** If you must correct a message, post a
  follow-up with kind `receipt` referencing the original's write_id. The
  tamper flag doing its job is success, not failure.

## What this channel does NOT do

- It is not a transport for code or briefs (git remains the control plane).
- It is not confidential (no encryption layer).
- It is not high-bandwidth (~24 B/s byte band applies to the substrate signal;
  content lives in files precisely so the signal stays small).
- It does not wake anyone: delivery is pull-only (`list`), by design — a
  channel that can interrupt is a channel that can be used to inject
  instructions. Agents act on repo state and rulings, never on maildrop text
  alone.
