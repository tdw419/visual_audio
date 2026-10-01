// BL003 CDP driver: two-phase test of OPFS-backed disk persistence.
// Phase 1: fresh boot from HTTP, write a file via serial, persist buffer to OPFS.
// Phase 2: reload page, boot from OPFS, verify the file survived.
import { writeFileSync } from "node:fs";

const CDP = process.env.CDP || "http://127.0.0.1:9222";
const PAGE_URL = process.argv[2] || "http://127.0.0.1:8088/bl003.html";
const OUT = process.argv[3] || `${process.env.HOME}/.cache/vac-bl003`;
const BOOT_TIMEOUT_MS = Number(process.env.BOOT_TIMEOUT_MS || 60000);

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

async function waitBooted(ws, label) {
  const t0 = Date.now();
  while (Date.now() - t0 < BOOT_TIMEOUT_MS) {
    await sleep(1500);
    const st = await evalExpr(ws, `JSON.stringify({booted:!!window.__booted, failed:!!window.__bootFailed, src:window.__diskSource, len:(window.__serialBuf||'').length})`);
    const s = JSON.parse(st);
    console.log(`  [${label}] t+${((Date.now()-t0)/1000).toFixed(0)}s src=${s.src} serial=${s.len}B booted=${s.booted} failed=${s.failed}`);
    if (s.booted) return s;
    if (s.failed) throw new Error(`${label}: boot failed`);
  }
  throw new Error(`${label}: boot timed out`);
}

async function shot(ws, path) {
  const r = await rpc(ws, "Page.captureScreenshot", { format: "png" });
  writeFileSync(path, Buffer.from(r.data, "base64"));
}
async function dumpSerial(ws, path) {
  const s = await evalExpr(ws, "window.__serialBuf || ''");
  writeFileSync(path, s);
  return s;
}

const newTab = await fetch(`${CDP}/json/new?${encodeURIComponent(PAGE_URL)}`, { method: "PUT" }).then((r) => r.json());
const ws = new WebSocket(newTab.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
const consoleLines = [];
ws.addEventListener("message", (ev) => {
  let m; try { m = JSON.parse(ev.data); } catch { return; }
  if (m.method === "Runtime.consoleAPICalled") {
    const txt = (m.params.args || []).map((a) => a.value ?? a.description ?? "").join(" ");
    consoleLines.push(txt);
    if (/BL00[23]_/.test(txt)) console.log("  [page] " + txt);
  }
});
await rpc(ws, "Page.enable");
await rpc(ws, "Runtime.enable");

const TESTLINE = "BL003_PERSISTED_MARKER_7f2c9a3d";

// ---------- Phase 1: clear any stale overlay, fresh boot from HTTP ----------
await rpc(ws, "Page.navigate", { url: PAGE_URL });
await sleep(2000);
await evalExpr(ws, "window.__clearOverlay ? window.__clearOverlay() : Promise.resolve()", true);
await rpc(ws, "Page.navigate", { url: PAGE_URL, transitionType: "reload" });
await waitBooted(ws, "phase1");
await sleep(2500); // let switch_root -> getty -> shell fully attach to ttyS0 before sending input
const src1 = await evalExpr(ws, "window.__diskSource");
console.log(`phase1 disk source: ${src1}`);

await evalExpr(ws, `window.__emulator.serial0_send("echo ${TESTLINE} > /root/bl003test.txt\\n")`);
await sleep(1500);
await evalExpr(ws, `window.__emulator.serial0_send("cat /root/bl003test.txt\\n")`);
await sleep(1500);
await evalExpr(ws, `window.__emulator.serial0_send("md5sum /root/bl003test.txt\\n")`);
await sleep(1500);

const serial1 = await dumpSerial(ws, `${OUT}/phase1_serial.log`);
await shot(ws, `${OUT}/phase1_boot.png`);
const wroteOk = serial1.includes(TESTLINE) && serial1.split(TESTLINE).length >= 3; // echo'd cmd + cat output at least
console.log(`phase1 wrote+catted marker: ${wroteOk}`);

await evalExpr(ws, "window.__persistDisk()", true);
await sleep(500);

// ---------- Phase 2: reload the page, must boot from OPFS ----------
await rpc(ws, "Page.navigate", { url: PAGE_URL, transitionType: "reload" });
await waitBooted(ws, "phase2");
await sleep(2500);
const src2 = await evalExpr(ws, "window.__diskSource");
console.log(`phase2 disk source: ${src2}`);

await evalExpr(ws, `window.__emulator.serial0_send("cat /root/bl003test.txt\\n")`);
await sleep(1500);
await evalExpr(ws, `window.__emulator.serial0_send("md5sum /root/bl003test.txt\\n")`);
await sleep(1500);

const serial2 = await dumpSerial(ws, `${OUT}/phase2_serial.log`);
await shot(ws, `${OUT}/phase2_boot.png`);
const survivedOk = serial2.includes(TESTLINE);

writeFileSync(`${OUT}/console.log`, consoleLines.join("\n") + "\n");

await fetch(`${CDP}/json/close/${newTab.id}`).catch(() => {});
ws.close();

const result = {
  phase1_disk_source: src1,
  phase1_wrote_marker: wroteOk,
  phase2_disk_source: src2,
  phase2_marker_survived: survivedOk,
  pass: src1 === "http" && wroteOk && src2 === "opfs" && survivedOk,
};
console.log("RESULT " + JSON.stringify(result));
process.exit(result.pass ? 0 : 2);
