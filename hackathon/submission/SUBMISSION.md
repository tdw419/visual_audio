# Bootable Images

**Track:** Indie Developer
**One sentence:** A GPU-native machine that reads its own poster — and writes it back.

## What it is

Bootable Images hides a machine-readable glyph code inside a poster. Meta's
image model (muse-image-1.0) paints the artwork; Meta's SAM 3.1 segments the
glyph cells back out of the pixels; our decoder recovers the hidden payload
byte-identically. The payload then boots the Linux kernel — 1.4 billion GPU-emulated
instructions on a WGSL compute shader — and reaches an interactive userspace
shell on the GPU core (receipted busybox session: uname, /proc/cpuinfo, free,
uptime, live prompt), every boot milestone deterministic. And the machine writes, too: a
sentence in English becomes glyph assembly via muse-spark-1.3, linted
against the machine's ISA conventions, executed on the canvas, halted clean.

"Here is a poster. Watch the machine read it. That was a computer."

## Demo video

[hackathon/demo/video/demo_v1.mp4](https://github.com/tdw419/visual_audio/blob/hackathon-submission/hackathon/demo/video/demo_v1.mp4) (60.7s). Every frame is a real artifact:
live-captured runs of the frozen one-command pipeline
([hackathon/demo/freeze/E2E.sh](https://github.com/tdw419/visual_audio/blob/hackathon-submission/hackathon/demo/freeze/E2E.sh), `FALLBACK_DEMO.sh`), the committed
art-blend poster, and the committed live-authoring artifact. Production
receipt: [hackathon/demo/video/PRODUCTION_RECEIPT.md](https://github.com/tdw419/visual_audio/blob/hackathon-submission/hackathon/demo/video/PRODUCTION_RECEIPT.md).

## Use of Meta AI tooling (beyond basic integration)

All live calls receipted with committed fixtures (hackathon/tests/fixtures/):

1. **muse-image-1.0 paints the demo poster** (art-blend asset decodes at 35%
   art share — receipts: muse_image_poster/RECEIPT.md)
2. **SAM 3.1 reads the pixels**: live segmentation with a pixel-exact box
   parse contract (c05132cc); characterized negative result on dense grids —
   which drove a hybrid architecture (SAM for poster structure, a pure-stdlib
   Otsu fallback for cell decode that works offline in 18ms)
3. **muse-spark-1.3 writes glyph assembly**: live English->asm->lint->
   execution receipts (MUSE_LIVE_AUTHORING_RECEIPT_2026-10-29.md, campaign
   2026-10-29); discovered and documented the reasoning_effort wire rule
   (minimal effort: 10x cheaper, 7x faster; "none" unsupported -> 400)
4. **The payload boots Alpine Linux on a GPU** — computation without pixels,
   verified by deterministic milestone logs across months of re-runs
   (18ms drift over 30+ days)

## Technical depth

- Byte-exact contract held end to end: payload -> Hilbert-mapped glyph grid
  -> poster pixels -> segmentation -> RLE -> bits -> GLY1 framing -> original
  bytes (md5-pinned, committed ground truth)
- Deterministic freeze: one command replays the whole demo against pinned
  hashes (h6), protected from drift by kernel-path rules
- Hybrid perception: a foundation vision model where it excels (poster
  geometry) and a 250-line classical fallback where it fails (dense grids),
  selected at runtime by a confidence gate
- Generated-code safety: model-written assembly is linted against
  machine-verified ISA conventions and executed against ground truth before
  it touches a canvas

## Where this is going

To be direct: today this is slower than a VM, and we are not claiming
boot-speed wins. The claim is architectural. A game server serves
thousands of players on one machine because each player costs a *view*,
not a computer — and this project has receipted the hard pieces of the
same model for desktops: a full Linux kernel and interactive shell
executing inside GPU compute, image I/O in both directions, and
byte-identical deterministic state on every boot. Because the entire
machine state is encapsulated in six GPU buffers, provisioning a new user
session collapses from an OS installation into a memory blit (68 min cold boot
→ 124 s snapshot resume → 76 ms per-seat in-VRAM clone; N=2 isolated seats from one
host process, zero cross-leakage — all measured on RTX 5090). One GPU serving many
desktops — each user's screen just an image, any device able to sit at
it — is the destination. Architectural analysis: [hackathon/submission/GAME_SERVER_OS_CONCEPT.md](https://github.com/tdw419/visual_audio/blob/hackathon-submission/hackathon/submission/GAME_SERVER_OS_CONCEPT.md).
The build order (persistent virtio root, N harts, framebuffer-as-image,
compositor-as-game-loop, deterministic migration) and the honest current
blockers are in [hackathon/submission/ROADMAP.md](https://github.com/tdw419/visual_audio/blob/hackathon-submission/hackathon/submission/ROADMAP.md).

## Impact

Teaches machines to treat images as computation — read, write, and boot
from pixels. The same pipeline gives any rendering system an external
verification oracle (pixels in, structure out, no shared assumptions with
the renderer), and gives any agent an authoring path from natural language
to verified machine code. Long-term, this is the I/O layer for GPU-native
computing: software that lives in, and is read back from, images.

## Verify it yourself

Don't take the video's word for anything — [hackathon/demo/VERIFY.md](https://github.com/tdw419/visual_audio/blob/hackathon-submission/hackathon/demo/VERIFY.md)
lists four self-service tests ranked by time to verdict: the pytest
suite (~7s), the offline glyph decode (~10s, no GPU), the one-command
end-to-end spine — decode + Linux kernel boot — (~90s, GPU), and the
live interactive shell: one command (`./hackathon/demo/BOOT_LINUX.sh`),
an unattended ~75-minute boot, then you type your own commands at
Linux on the GPU core (`ls`, `cat`, `free`, the whole busybox toolbox
— committed transcript:
[hackathon/tests/fixtures/gpu_shell_live_interactive_2026-11-01.log](https://github.com/tdw419/visual_audio/blob/hackathon-submission/hackathon/tests/fixtures/gpu_shell_live_interactive_2026-11-01.log)).
The committed shell transcript
([hackathon/tests/fixtures/gpu_shell_session_2026-10-30.log](https://github.com/tdw419/visual_audio/blob/hackathon-submission/hackathon/tests/fixtures/gpu_shell_session_2026-10-30.log)) and the
scene-to-artifact production receipt let you audit the video frame by
frame without running anything.
