# RESEARCH — BK-60 L4 oracle numbers re-measured under the corrected harness:
# D2/D4 confirmed with real attributions; D3 FLIPS — the oracle itself allows
# a USER paged read into the config window (both engines agree)

- Tick: 2026-09-27 ~22:0x CDT, builder af3e62239ce2 (Glyph OS Event Chain cron)
- HEAD at claim: 1606834c (mailbox re-verified: newest RULING mtime 1790550013
  < HEAD commit time 1790561796 — clean; QUEUE_STATE.json: 0 non-landed items;
  all three remedy-* tickets landed → Phase 1c eligible)
- QUESTION (deferred by .builder_queue/RESEARCH_d1_paged_fault_attribution_
  af3e.md F4 and BK-60's amendment): the original BK-60 probe's oracle-side
  fault_addr values for D2 (12288) and D3 (12304) were pt_tag_mismatch
  ARTIFACTS — every CPU paged leg died at the tag gate (glyph_isa_v2.py:92-95)
  BEFORE the PTE checks. What does the oracle ACTUALLY do for D2/D3/D4 when
  the harness passes the tag gate (image contains the PT window, data words
  RAM-seeded)? No later RESEARCH_*/backlog row answers this; net-new.

## METHOD

- Probe: .builder_queue/probe_bk60_l4_oracle_af3e.py (untracked, landed
  modules only, HEAD 1606834c). Same five leg programs as the original
  probe (D1 control, D2 U-clear, D3 MMIO-through-PTE, D4 unmapped ST,
  C1 unpaged E-K1), CORRECTED HARNESS ONLY: min_rows=64 → 32x64 = 2048-word
  image (asserted >= 1549 unwrapped), receipt vpn 2 identity-mapped
  (F3 posture), canary/box words via drive(seeds=) / ram_seed (matched
  channels), PT tag+arm+PTEs stamped into image pixels (GH-25 discipline),
  USER via MODE_LATCH+KJMP. fault_reason captured via manual step-loop on
  the same PNG bytes (probe defect #4 workaround). 3 runs byte-identical,
  results_md5 da02059b4c521f46ffebb96cc68ace46.
- Harness discriminating evidence (built-in, no mutation needed): the
  fault_reason strings THEMSELVES prove the tag gate passed — D2 reads
  "pte_invalid pte=0xc03 ... op=LD" and D4 "pte_invalid pte=0x0 ... op=ST"
  (PTE-class faults, reachable only past check_pt_tag), vs the original
  harness's "pt_tag_mismatch got=0x0 expected=0x505447". C1 (no arm/tag,
  unpaged out-of-box ST) independently faults E-K1 style with fault_addr
  400 — the fence still fires under this harness; the harness does not
  mask violations.

## FINDINGS

F1 — D2 (PTE V|W, U clear, USER LD): oracle faults for the RIGHT reason
now: fault_reason "pte_invalid pte=0xc03 vaddr=0x3000 mode=USER op=LD
site=glyph_isa_v2" (glyph :872-876 PTE_U check), fault_addr 12288, mode
SUPER at fault, 20 steps. The original receipt's D2 fault_addr 12288 is
numerically unchanged but REATTRIBUTED (tag artifact → real PTE_U denial).
Twin on the matched harness: r10==0x0ADF00D, receipt_720==4660, 24 steps,
no fault channel — admits the read. DIVERGENCE CONFIRMED (L1's RED target
stands, now with a correct oracle pin).

F2 — D3 (PTE V|W|U pfn 32, USER LD of word 8196 THROUGH translation):
FLIPPED. Oracle runs CLEAN: faulted=False, r10==1300 (the config word,
seeded via RAM), receipt_720==4660, 24 steps, mode USER. The original
receipt's "oracle faulted 12304" was ENTIRELY the tag artifact. Source
explains it: the paged-translation exemption at glyph_isa_v2.py:836/:968
is `not (mode==SUPER and addr in MMIO window)` — a USER paged access is
NEVER exempted from translation and the paged LD path has NO box consult
(:872-914: PTE checks then plain/pfn resolve; no _addr_in_box call). Both
engines now measured AGREEING: a USER task with a plain PTE targeting the
BOX0_HI config word reads it through translation on the oracle AND the twin.
CONSEQUENCES: (a) D3 RETIRES as an engine divergence — BK-60's L2 ("paged
USER LD resolving into words 8192+ must return 0 or fault") has NO oracle-
parity target to pin; the twin behaves identically to the oracle. (b) The
open question moves from "twin defect" to POSTURE: RULING_BK38_READ_POSTURE's
F1 read posture (config words unreadable in USER) is violated by the ORACLE's
own paged path, not just the twin's — the unpaged BK-56 fix (:361-363
unpaged branch) does not extend to the paged branch. Whether the paged path
SHOULD consult boxes is a ruling-level decision (skeleton-sign-off change to
BK-60's L2 shape), not something the lane self-applies.

F3 — D4 (PTE 0, USER paged ST): oracle faults for the right reason:
"pte_invalid pte=0x0 vaddr=0x3000 mode=USER op=ST site=glyph_isa_v2"
(:997-1006), fault_addr 12288, 21 steps. Twin: silent drop confirmed on the
matched harness — no fault channel, r10==0, receipt_720==4660 (walks to the
epilogue), ram_3072 stays 0 (value nowhere), 25 steps. DIVERGENCE CONFIRMED
(L3's RED target stands: oracle records a fault the twin never emits — a
kernel reading FAULT_ADDR sees different machine state per engine).

F4 — C1 (unpaged out-of-box USER ST, control): oracle fault_addr 400
(matches the original receipt's oracle side); twin refuses at 18 steps
(matches). NEW small fact: the oracle's unpaged E-K1 ST fence site
(:1075-1076) does NOT set fault_reason — the 5-site classification pass
(glyph :876/:1006 comments) covered only the paged pte_invalid sites. A
manual step-loop on a C1 fault reads fault_reason=None despite
faulted=True. Cosmetic (fault_addr + FAULT_ADDR_ADDR word are correct),
but it is the same receipt-hygiene gap probe defect #4 hit, at one more
site.

## BK-60 GATE CONSEQUENCE (proposed, not self-applied beyond the row note)

- L1 (U-bypass): unchanged; oracle pin now "pte_invalid op=LD, pte=<val>,
  fault_addr 12288" measured, not inferred.
- L2 (MMIO-through-PTE): premise REWRITTEN — both engines allow; the leg
  becomes an oracle-parity PIN (both must return the word, catching an
  accidental future box-consult asymmetry) plus a flagged POSTURE question
  for a RULING if Jericho wants paged reads into 8192+ fenced.
- L3 (silent unmapped ST): unchanged; oracle pin measured
  (pte_invalid op=ST, 12288).
- L4 (oracle-parity): satisfied by THIS receipt's numbers under the
  corrected harness; the amendment's min_rows/RAM-seed posture requirement
  is proven sufficient (3x byte-identical).

## VERIFICATION STATUS

- Shown able to fail/discriminate: D2 and D4 fault legs fire (the probe is
  not an always-pass harness); C1 proves the unpaged fence still traps under
  this harness; D3's clean result is the OPPOSITE of the original receipt's
  claim — the probe demonstrably returns verdicts that contradict the prior
  receipt rather than echoing it.
- What this PASS does NOT prove: no engine or shader code changed (research
  receipt — proposes, never lands); the twin-side divergence measurements
  are re-confirmations on a matched harness, not an independent replication
  of the original WGSL probe's full S-leg source audit; the C1 oracle steps
  counter in the drive() receipt reads 4000 (receipt bookkeeping after the
  fault — not investigated; the fault_addr/verdict fields are the datum);
  PTE_HILB/PTE_PIX frame paths untouched; paged×tile composition unprobed.
- Rule-1 floors: no rates, costs, or timing claims — all numbers structural
  (word values, fault strings, step counts, md5s). Floors do not attach.

## ARTIFACTS

- .builder_queue/probe_bk60_l4_oracle_af3e.py — 3x
  da02059b4c521f46ffebb96cc68ace46 (fresh PNG per run at /tmp/bk60_l4_*)
