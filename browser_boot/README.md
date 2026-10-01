# browser_boot/ — Phase 27 harness

Boot a real Linux kernel inside a headless browser tab and capture a receipt.
Backs ROADMAP Phase 27 (TASK_BL001 … TASK_BL004).

## What's here

| File | Purpose |
|------|---------|
| `index.html` | v86 boot page. Wires `serial0` output into `window.__serialBuf`, sets `window.__booted` when a userspace marker appears, mirrors markers to `console.log` for CDP capture. |
| `drive.mjs` | Dependency-free CDP driver (Node 24 global `fetch` + `WebSocket`). Opens the page in a running headless Chrome, polls for `__booted`, writes `boot.png` + `serial.log` + `console.log`, prints `RESULT {json}`, exits 0 on boot / 2 on timeout. |
| `launch-chrome.sh.example` | Template for the headless Chrome launch. `--no-sandbox` is required here: Ubuntu ships `apparmor_restrict_unprivileged_userns=1`, which crashes Chrome's namespace sandbox. |
| `receipts/` | BL001 output: `boot.png` (1280×757), `serial.log`, `console.log`. |

Vendored binaries (`libv86.js`, `v86.wasm`, `seabios.bin`, `vgabios.bin`, `linux.iso`)
are **not** committed — fetch them into a scratch dir (see below).

## Environment notes (2026-09-04, this host)

- **No Google Chrome** at `/opt/google/chrome/chrome` — the ecc `chrome-devtools`
  MCP's default. Snap Chromium exists but confinement blocks it from writing
  screenshot/profile paths outside `~/snap/chromium/`.
- Fix: userspace **Chrome-for-Testing**, no root, no snap:
  ```
  npx -y @puppeteer/browsers install chrome@stable --path ~/.cache/puppeteer
  ```
- The ecc MCP was repointed at the running browser by adding
  `--browserUrl=http://127.0.0.1:9222` to its args in
  `~/.claude/plugins/cache/ecc/ecc/<ver>/.mcp.json` (fragile — an ecc upgrade
  overwrites it). The harness here does **not** need the MCP; it speaks CDP directly.

## Reproduce BL001

```bash
export BL_DIR=~/.cache/vac-bl001
export CHROME=~/.cache/puppeteer/chrome/linux-*/chrome-linux64/chrome
mkdir -p "$BL_DIR/site" "$BL_DIR/profile"
HARNESS="$PWD"              # run this from browser_boot/
cd "$BL_DIR/site"

# assets
npm pack v86 && tar xzf v86-*.tgz
cp package/build/libv86.js package/build/v86.wasm .
curl -sO https://copy.sh/v86/bios/seabios.bin
curl -sO https://copy.sh/v86/bios/vgabios.bin
curl -s -o linux.iso https://copy.sh/v86/images/linux.iso
cp "$HARNESS/index.html" .

# browser
"$CHROME" --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --remote-debugging-port=9222 --user-data-dir="$BL_DIR/profile" about:blank &

# serve + drive
python3 -m http.server 8087 --bind 127.0.0.1 &
node "$HARNESS/drive.mjs" http://127.0.0.1:8087/index.html "$BL_DIR"
```

Expected `RESULT`: `{"booted":true,"boot_ms":~4000,...}` and a `boot.png`
showing `VFS: Mounted root (ext2 filesystem)` followed by a `/root%` shell.

## Next (BL002)

`drive.mjs` + `index.html` are the reusable surface. BL002 swaps `cdrom:{url:...}`
for a virtio-blk disk built from `alpine_rootfs_3mb.img` roundtripped through
`tools/dense_encoder.py`, and asserts sha256 equality before boot.
