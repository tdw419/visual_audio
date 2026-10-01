// BL005 CDP driver: assemble the boot disk purely from HTTP Range fetches
// against a VAC1 MKV container, capture every network request during that
// phase (must be only disk.mkv + disk.manifest.json — zero .img/.wav),
// verify the assembled buffer's sha256 against the manifest, then confirm
// the guest actually boots from it.
//
// Usage: node bl005_drive.mjs [pageUrl] [outDir]
import { writeFileSync } from "node:fs";

const CDP = process.env.CDP_URL || "http://127.0.0.1:9222";
const PAGE_URL = process.argv[2] || "http://127.0.0.1:8089/bl005.html";
const OUT = process.argv[3] || `${process.env.HOME}/.cache/vac-bl005/receipt`;
const BOOT_TIMEOUT_MS = Number(process.env.BOOT_TIMEOUT_MS || 120000);

let _id = 0;
function rpc(ws, method, params = {}) {
  const id = ++_id;
  return new Promise((resolve, reject) => {
    const on = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      if (m.id !== id) return;
      ws.removeEventListener("message", on);
      m.error ? reject(new Error(method + ": " + JSON.stringify(m.error))) : resolve(m.result);
    };
    ws.addEventListener("message", on);
    ws.send(JSON.stringify({ id, method, params }));
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function evalExpr(ws, expression, awaitPromise = false) {
  const r = await rpc(ws, "Runtime.evaluate", { expression, returnByValue: true, awaitPromise });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
  return r.result.value;
}

const newTab = await fetch(`${CDP}/json/new?${encodeURIComponent(PAGE_URL)}`, { method: "PUT" }).then((r) => r.json());
const ws = new WebSocket(newTab.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

const requests = []; // {url, method, range}
const consoleLines = [];
ws.addEventListener("message", (ev) => {
  let m; try { m = JSON.parse(ev.data); } catch { return; }
  if (m.method === "Network.requestWillBeSent") {
    const r = m.params.request;
    requests.push({ url: r.url, method: r.method, range: r.headers["Range"] || r.headers["range"] || null });
  }
  if (m.method === "Runtime.consoleAPICalled") {
    const txt = (m.params.args || []).map((a) => a.value ?? a.description ?? "").join(" ");
    consoleLines.push(txt);
    if (/BL00[25]_/.test(txt)) console.log("  [page] " + txt);
  }
});

await rpc(ws, "Page.enable");
await rpc(ws, "Runtime.enable");
await rpc(ws, "Network.enable");
await rpc(ws, "Page.navigate", { url: PAGE_URL });

// ---- Phase 1: fetch/assembly. Requests here must be ONLY disk.mkv ranges
// (plus the two small JSON/CORS preambles). No disk image may be fetched.
const tFetch0 = Date.now();
let fetchDone = false;
while (Date.now() - tFetch0 < BOOT_TIMEOUT_MS) {
  fetchDone = await evalExpr(ws, "window.__fetchDone === true");
  if (fetchDone) break;
  await sleep(500);
}
if (!fetchDone) throw new Error("fetch phase timed out");
const fetchMs = Date.now() - tFetch0;

const assemblyRequests = requests.map((r) => r.url);
// The DISK must come only from the MKV. The kernel/initrd/BIOS/wasm runtime
// are legitimately fetched as files by v86 (identical to BL004) — the gate
// below bans disk-image formats, not the emulator's own boot files.
const mkvRangeFetches = requests.filter((r) => r.url.includes("disk.mkv") && r.range).length;
const manifestFetches = requests.filter((r) => r.url.includes("disk.manifest.json")).length;
const forbidden = assemblyRequests.filter((u) => /\.(img|wav)(\?|$)/.test(u));

const state = await evalExpr(ws, `JSON.stringify({
  sha256: window.__diskSha256,
  crcFailures: window.__crcFailures,
  frameTimings: window.__frameTimingsMs,
})`).then(JSON.parse);

// sha256 gate: page-assembled buffer must equal the manifest value.
const manifest = await fetch(PAGE_URL.replace(/bl005\.html$/, "disk.manifest.json")).then((r) => r.json());
const sha256Match = state.sha256 === manifest.sha256;

console.log(`fetch phase: ${fetchMs}ms, ${mkvRangeFetches} mkv Range GETs, ` +
            `${manifestFetches} manifest fetch(es), forbidden=${forbidden.length}`);
console.log(`sha256 assembled=${state.sha256}`);
console.log(`sha256 manifest=${manifest.sha256}`);
console.log(`crc_failures=${state.crcFailures} sha256Match=${sha256Match}`);

// ---- Phase 2: wait for userspace in the guest.
const tBoot0 = Date.now();
let booted = false, bootFailed = false;
while (Date.now() - tBoot0 < BOOT_TIMEOUT_MS) {
  const s = await evalExpr(ws, "({booted: !!window.__booted, failed: !!window.__bootFailed})");
  booted = s.booted; bootFailed = s.failed;
  if (booted || bootFailed) break;
  await sleep(1000);
}
const serialTail = await evalExpr(ws, "window.__serialBuf.slice(-3000)");

const timings = state.frameTimings;
const avgMs = timings.length ? timings.reduce((a, b) => a + b, 0) / timings.length : -1;
const receipt = {
  task: "BL005",
  page_url: PAGE_URL,
  fetch_phase_ms: fetchMs,
  mkv_range_fetches: mkvRangeFetches,
  manifest_fetches: manifestFetches,
  forbidden_requests: forbidden,
  crc_failures: state.crcFailures,
  sha256_assembled: state.sha256,
  sha256_manifest: manifest.sha256,
  sha256_match: sha256Match,
  userspace_reached: booted,
  boot_failed: bootFailed,
  boot_ms: booted ? Date.now() - tBoot0 : null,
  frame_count: timings.length,
  frame_avg_ms: Number(avgMs.toFixed(3)),
  frame_min_ms: timings.length ? Math.min(...timings) : null,
  frame_max_ms: timings.length ? Math.max(...timings) : null,
  serial_tail: serialTail,
  console_tail: consoleLines.slice(-30),
};
writeFileSync(OUT, JSON.stringify(receipt, null, 1));
console.log(`\nreceipt -> ${OUT}`);
console.log(`userspace_reached=${booted} boot_failed=${bootFailed}`);

const pass = sha256Match && state.crcFailures === 0 && forbidden.length === 0 && booted && !bootFailed;
console.log(pass ? "BL005_PASS" : "BL005_FAIL");
process.exit(pass ? 0 : 1);
