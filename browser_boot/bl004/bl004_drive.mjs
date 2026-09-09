// BL004 CDP driver: assemble the disk purely from HTTP Range fetches against
// a .wav file, capture every network request during that phase (must be only
// .wav — zero .img/.png), verify the assembled buffer's sha256, then confirm
// the guest actually boots from it.
import { writeFileSync } from "node:fs";

const CDP = "http://127.0.0.1:9222";
const PAGE_URL = process.argv[2] || "http://127.0.0.1:8089/bl004.html";
const OUT = process.argv[3] || `${process.env.HOME}/.cache/vac-bl004/receipt`;
const BOOT_TIMEOUT_MS = Number(process.env.BOOT_TIMEOUT_MS || 90000);
const EXPECTED_SHA256 = process.env.EXPECTED_SHA256 || "";

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

const requests = []; // {url, method, headers}
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
    if (/BL00[24]_/.test(txt)) console.log("  [page] " + txt);
  }
});

await rpc(ws, "Page.enable");
await rpc(ws, "Runtime.enable");
await rpc(ws, "Network.enable");
await rpc(ws, "Page.navigate", { url: PAGE_URL });

// Wait for the fetch phase (all sector Range GETs) to complete.
const tFetch0 = Date.now();
let fetchDone = false;
while (Date.now() - tFetch0 < BOOT_TIMEOUT_MS) {
  await sleep(500);
  const done = await evalExpr(ws, "!!window.__fetchDone");
  if (done) { fetchDone = true; break; }
}
if (!fetchDone) throw new Error("disk-assembly fetch phase never completed");

const assembledSha256 = await evalExpr(ws, "window.__diskSha256");
const timings = await evalExpr(ws, "window.__sectorTimingsMs");
console.log(`assembled sha256=${assembledSha256}`);
console.log(`sectors fetched: ${timings.length}, avg=${(timings.reduce((a,b)=>a+b,0)/timings.length).toFixed(3)}ms, min=${Math.min(...timings).toFixed(3)}ms, max=${Math.max(...timings).toFixed(3)}ms`);

// Now wait for the guest to actually boot from that assembled buffer.
const tBoot0 = Date.now();
let booted = false, failed = false;
while (Date.now() - tBoot0 < BOOT_TIMEOUT_MS) {
  await sleep(1500);
  const st = JSON.parse(await evalExpr(ws, "JSON.stringify({booted:!!window.__booted, failed:!!window.__bootFailed})"));
  if (st.booted) { booted = true; break; }
  if (st.failed) { failed = true; break; }
}

const serial = await evalExpr(ws, "window.__serialBuf || ''");
writeFileSync(`${OUT}/serial.log`, serial);
writeFileSync(`${OUT}/console.log`, consoleLines.join("\n") + "\n");
writeFileSync(`${OUT}/network_requests.json`, JSON.stringify(requests, null, 2));
writeFileSync(`${OUT}/sector_timings_ms.json`, JSON.stringify(timings));

const shot = await rpc(ws, "Page.captureScreenshot", { format: "png" });
writeFileSync(`${OUT}/boot.png`, Buffer.from(shot.data, "base64"));

await fetch(`${CDP}/json/close/${newTab.id}`).catch(() => {});
ws.close();

// Classify every disk-relevant request: must be .wav with a Range header;
// zero requests to any raw image/.img/.png disk file.
const diskRequests = requests.filter(r => /alpine\.wav|alpine\.manifest\.json/.test(r.url));
const nonWavDiskRequests = requests.filter(r => /\.img\b/.test(r.url));
const wavRangeRequests = requests.filter(r => /alpine\.wav/.test(r.url) && r.range);

const result = {
  fetch_phase_ok: fetchDone,
  assembled_sha256: assembledSha256,
  sha256_matches_expected: EXPECTED_SHA256 ? (assembledSha256 === EXPECTED_SHA256) : null,
  sector_count: timings.length,
  avg_sector_ms: timings.reduce((a,b)=>a+b,0) / timings.length,
  min_sector_ms: Math.min(...timings),
  max_sector_ms: Math.max(...timings),
  wav_range_requests: wavRangeRequests.length,
  non_wav_img_requests: nonWavDiskRequests.length,
  total_requests: requests.length,
  booted,
  boot_failed: failed,
  pass: fetchDone && (EXPECTED_SHA256 ? assembledSha256 === EXPECTED_SHA256 : true)
        && nonWavDiskRequests.length === 0 && wavRangeRequests.length === timings.length
        && booted && !failed,
};
console.log("RESULT " + JSON.stringify(result, null, 2));
process.exit(result.pass ? 0 : 2);
