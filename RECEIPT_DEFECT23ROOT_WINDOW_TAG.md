
## Post-landing verification note (2026-09-14, orchestrator)

- Landed as 13d94a9; twins byte-identical, hook differential 37/37.
- WGSL scope note: glyph_dispatch/src/glyph/wgsl_glyph_isa_v2.py is a separately-evolved
  variant (pre-differed from tools/wgsl_glyph_isa_v2.py before this change; NOT under the
  byte-sync obligation). It is tag-agnostic - its walk reads pt_base+vpn only, never
  pt_base-1 - so stamped tables remain inert/correct on the GPU path. If GPU-side
  container validation is ever wanted, the PAGE_TABLE_TAG check must be ported there
  deliberately; absence today is by design, not an omission of this commit.
