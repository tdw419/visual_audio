# RECEIPT — h8 demo video v1 (operator-produced, no human input)

demo_v1.mp4: 60.7s, 1920x1080, h264+aac, 0.9MB.

## Every frame is a real artifact
- s1 title card
- s2: the committed poster (muse-image-1.0 art + glyph overlay,
  fixtures/muse_image_poster/poster_art_blend_65.png)
- s3: LIVE captured output of FALLBACK_DEMO.sh (pixels path, md5
  cf09b99d... == gt, eta 0.898, 0.018s wall) — run during production
- s4: LIVE captured frozen E2E decode JSON (path sam, md5 3292333c... ==
  gt)
- s5: LIVE captured E2E boot leg (kernel banner 6.12.31-lts, smp up,
  rc 0, 83.2s wall, within budget)
- s6: the committed live-authoring artifact (muse_gen_5.asm, campaign
  2026-10-29: lint 0 issues, HALT at 650 steps)
- s7 spine close

## Narration
Piper en_GB-alan (local, offline) - edge-tts was 403-blocked externally.

## Production chain
frames: PIL-rendered 1920x1080 stills from captured text/images;
assembly: ffmpeg concat (stills + narration, per-scene durations).
Nothing on screen is simulated; every line traces to a committed receipt
or a run executed during production.

# v2 (same artifacts, motion + reveal)

demo_v2.mp4: 64.3s, 1.1MB, 8fps frame-sequenced.
Upgrades over v1: poster composite animates (art fades in, glyph grid
fades over to the 65% blend); every terminal scene is a progressive
typing reveal of the same live captured output (no lines invented; reveal
order = capture order); PASS/md5/HALT lines accent-colored; fades on
open/close. Audio identical (piper en_GB-alan). Verified: 16 sampled
frames all distinct, per-scene audio durations match narration + pad.
Nothing on screen is simulated: same receipts, animated.

# v3 (the machine working, not explained)

demo_v3.mp4: 59.5s, 4.4MB. Responds to the note that v1/v2 explained
instead of showed. Three scenes are now live instrument views of real
execution state:

- READ (s3): the canonical poster on screen while the REAL Otsu-classified
  grid (glyph_decoder.otsu + per-cell mean, same code path as
  decode_poster_pixels) is walked in Hilbert order; box overlay is the
  recorded SAM fixture box; ends on the 58-byte payload + md5 match.
- BOOT (s4): the actual serial log from the E2E run
  (/tmp/hackathon_e2e_out.Op62/serial.log, sha256 c9402658..., 133 lines,
  OpenSBI 1.7 -> kernel 6.12.31-0-lts -> smp up), scrolled as a
  time-lapse, milestones accent-colored. Labeled time-lapse on screen.
- WRITE (s5): muse_gen_5.asm placed and executed on GlyphCPUv2 during
  production; the 64 memory squares fill in sync with the machine's real
  write sequence (snapshot of nonzero memory words after each executed
  step, 650 steps, HALT a0=64). Every square is a real machine write.

Every animated pixel traces to execution state captured during
production; no simulated output anywhere. v1/v2 retained for comparison.

# v4 (the human-judge cut)

demo_v4.mp4: 59.5s, 1.05MB. Response to feedback that v3 read as
designed for machines: same real execution state, staged for a person.
- One idea per beat, big type, dip-to-black transitions between scenes.
- s2: full-screen muse-image poster with slow zoom; captions do the work.
- s3: scan-line sweep over the poster (same real Otsu grid + SAM fixture
  box as v3, presented as cinema not data panels); verdict card: 58
  bytes, md5 matches.
- s4: three big milestone lines (real serial values: 6.12.31-0-lts, smp
  up, 1.4B steps / 83s) with a dim two-line live serial strip at the
  bottom for authenticity.
- s5: the English sentence on screen, then the 64 real GlyphCPUv2
  memory writes paint a banner across the screen (same write-sequence
  capture as v3), ending HALT card.
Narration and every artifact identical to v3; only staging changed.
v1-v3 retained.

# v5 (v3 cut + the two chapters Jericho asked for)

demo_v5.mp4: 101.9s, 5.1MB. Jericho preferred v3's terminal aesthetic;
v5 keeps all six v3 scenes (same frames) and adds:

- STORAGE (s3b, 23s): how information lives in the image — real Otsu
  grid, one zoomed 8x8 cell -> 1 bit (ink=1), the Hilbert walk drawn
  across the grid to 512 cells, then the REAL framed bytes typed out:
  47 4c 59 31 = "GLY1" magic, length 58, then ASCII "hello from the
  glyph poster" (the actual committed payload), md5 match card.
- SHELL (s4b, 19s): how to boot and use Linux — the real h12 session
  transcript (receipt a61fa614): Run /init, GPU userspace shell banner,
  uname -a, /proc/cpuinfo hart 0 rv64imafdc, free, uptime, live prompt.

Narration: piper segments s3c/s4c (new), reused v3 segments elsewhere.
Every byte shown traces to the committed fixture (glyph_poster_gt.png ->
decode_poster_pixels -> framed payload) or the committed shell receipt.
v1-v4 retained.

# v6 (v5 + a real usage session in the shell chapter)

demo_v6.mp4: 101.9s, 5.1MB. Responds to "the demo needs something that
tells judges and users how to actually use the booted Linux."
- s4b shell chapter re-rendered from the second committed session
  (gpu_shell_session_2026-10-30.log, superseding the shorter first one):
  after uname/cpuinfo, the session now WRITES a file and reads it back
  (echo 'hello GPU' > note.txt && cat), lists / (note.txt visible), and
  computes (expr 40 + 2 -> 42) before the interactive prompt.
- Usage is now demonstrated, not asserted. All transcript lines verbatim
  from the committed log.
- Also shipped for users: tools/build_gpu_shell_blob.py +
  hackathon/demo/SHELL_QUICKSTART.md (reproduce the boot in 3 commands).

# v7 (v6 + "test it yourself" endcard)

demo_v7.mp4: 122.2s, 5.3MB. Responds to "the demo needs to tell judges
how to TEST it, to prove it works." New closing scene (real outputs
captured today on the current HEAD):
- $ ./hackathon/demo/freeze/E2E.sh -> E2E PASS line verbatim
  (decode md5 3292333c... | boot rc 0 | 80.8s wall)
- $ python3 -m pytest hackathon/tests/ -q -> 59 passed in 7.32s
- footer: hackathon/demo/VERIFY.md | boot the shell and type
Narration s7v (19.0s, piper). Ships with hackathon/demo/VERIFY.md
(4 ranked judge-facing tests) + SUBMISSION.md "Verify it yourself"
section + scanner word-boundary fix (test_meta_client.py, false
positive on boot log "mask:"/"disk " tokens; suite 59/59).

# v8 (v7 + interactive-shell beat in the testing endcard)

demo_v8.mp4: 140.3s, 5.6MB. New closing scene s8v "Or type at it
yourself": the two live-driver commands, then the REAL interactive
transcript (ls / with note.txt, cat note.txt -> hello GPU, free -> real
Mem table) verbatim from the committed receipt
hackathon/tests/fixtures/gpu_shell_live_interactive_2026-11-01.log
(commit 9d012168). Footer points at VERIFY.md (four ranked tests).
Narration s8v (16.9s, piper).

# v9 (v8 with the one-command boot in the endcard)

demo_v9.mp4: 140.3s, 5.6MB. s8v re-rendered around the new judge-facing
launcher: "$ ./hackathon/demo/BOOT_LINUX.sh" (hackathon/demo/BOOT_LINUX.sh,
commit this cycle) instead of the two raw commands; same receipted
interactive transcript and narration. v8 retained.

# v10 (v9 + "Where this is going" roadmap closer)

demo_v10.mp4: 170.2s, 6.0MB. New final scene s9v responding to "the
demo should include where we intend to take the project": honest
opening line ("slower than a VM - we are not claiming boot speed"),
the destination (one GPU serving many desktops like a game server
serves players; each screen an image), the receipted foundations, and
the build order (virtio root -> N harts -> framebuffer-as-image ->
served desktops). Content mirrors hackathon/submission/ROADMAP.md.
Narration s9v (28.6s, piper).
