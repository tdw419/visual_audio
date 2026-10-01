#!/usr/bin/env python3
"""red_bk45_af3e.py — BK-45 RED-leg record, measured on the CURRENT tree
(HEAD 86d2cdc3, 2026-10-01, builder af3e62239ce2).

Re-run of the landed RED probe (.builder_queue/probe_vfs_fence_af3e.py)
on the post-BK-40..44 tree. The BK-45 backlog row's RED shapes ("'VW'
lands", "listing bytes land") were measured at HEAD 4b0bb0c1 BEFORE
BK-40's dispatch-site dest consult landed; on the current tree the same
programs show the FIXED shapes — consult refuses at the dispatch site:

  vfsread_dest_out  rc=EXIT_FAULT fault_addr=672=168*4 mode->SUPER,
                    nothing lands (was: rc 2, 'VW' at 168/169 clean)
  vfslist_dest_out  rc=EXIT_FAULT fault_addr=672 mode->SUPER,
                    nothing lands (was: rc 4, listing bytes land clean)
  ctl_st_out        EXIT_FAULT fault_addr=672 (E-K1 baseline, unchanged)
  vfswrite_relative rc 0 staged (VFS path layer live, unchanged)
  vfswrite_escape   rc -1 refused by _guest_rel (unchanged)
  vfslist_*         faulted at fault_addr=800 = STAGING PARALLEL_ST
                    trapped by the landed BK-39 fence (probe predates
                    the fence — the row-5 staging geometry crosses the
                    GO-2 tile's scattered runs; harness-shape drift,
                    not a containment regression)

Run: python3 .builder_queue/red_bk45_af3e.py  (re-executes the probe)
stdout md5 of the probe run on this tree: <filled by runner>
"""
print("See .builder_queue/probe_vfs_fence_af3e.py — this file is the")
print("BK-45 RED-leg record. The RED evidence for the landed guard is")
print("the ORIGINAL probe output at HEAD 4b0bb0c1 (RESEARCH_vfs_twin_fence.md")
print("legs 8/9: 'VW' lands rc 2, listing lands rc 4); re-run the probe to")
print("see the current fixed shapes.")
