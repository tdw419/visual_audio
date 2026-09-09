
## [2026-09-07 21:17 CDT] Almost asked: whether to adopt the dirty tree (rv64i_to_glyph.py +83 lines, glyph_ir.py untracked)
**Decided instead:** defer per DIRTY TREE rule — mtimes were seconds old, clearly active GH-15 session work
**Reason:** stall rule only applies when frozen >30min; tree is mid-edit by the session that committed fcdc29a
**Outcome:** deferred cleanly; will claim next unclaimed item on next wake if tree is clean
