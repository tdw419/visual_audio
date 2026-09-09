// BL001 CDP driver: open the v86 boot page in the running headless Chrome,
// wait for a userspace marker on serial, capture screenshot + serial log.
// No deps — Node 24 global fetch + WebSocket.
import { writeFileSync } from "node:fs";

const CDP = process.env.CDP || "http://127.0.0.1:9222";
const PAGE_URL = process.argv[2] || "http://127.0.0.1:8080/index.html";
const OUT = process.argv[3] || `${process.env.HOME}/.cache/vac-bl001`;
const TIMEOUT_MS = Number(process.env.BOOT_TIMEOUT_MS || 120000);

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

const newTab = await fetch(`${CDP}/json/new?${encodeURIComponent(PAGE_URL)}`, { method: "PUT" })
  .then((r) => r.json());
console.log("tab:", newTab.id, newTab.webSocketDebuggerUrl);

const ws = new WebSocket(newTab.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

const consoleLines = [];
ws.addEventListener("message", (ev) => {
  let m; try { m = JSON.parse(ev.data); } catch { return; }
  if (m.method === "Runtime.consoleAPICalled") {
    const txt = (m.params.args || []).map((a) => a.value ?? a.description ?? "").join(" ");
    consoleLines.push(txt);
    if (/BL001_/.test(txt)) console.log("  [page] " + txt);
  }
});

await rpc(ws, "Page.enable");
await rpc(ws, "Runtime.enable");
await rpc(ws, "Page.navigate", { url: PAGE_URL });

const t0 = Date.now();
let state = {};
while (Date.now() - t0 < TIMEOUT_MS) {
  await sleep(2000);
  const r = await rpc(ws, "Runtime.evaluate", {
    expression: `JSON.stringify({booted:!!window.__booted, ms:window.__bootMs||0,
      len:(window.__serialBuf||'').length, tail:(window.__serialBuf||'').slice(-160)})`,
    returnByValue: true,
  });
  try { state = JSON.parse(r.result.value); } catch { state = { raw: r.result.value }; }
  console.log(`  t+${((Date.now() - t0) / 1000).toFixed(0)}s serial=${state.len}B booted=${state.booted}`);
  if (state.booted) break;
}

const serial = await rpc(ws, "Runtime.evaluate", {
  expression: "window.__serialBuf || ''", returnByValue: true,
}).then((r) => r.result.value || "");
writeFileSync(`${OUT}/serial.log`, serial);
writeFileSync(`${OUT}/console.log`, consoleLines.join("\n") + "\n");

const shot = await rpc(ws, "Page.captureScreenshot", { format: "png" });
writeFileSync(`${OUT}/boot.png`, Buffer.from(shot.data, "base64"));

await fetch(`${CDP}/json/close/${newTab.id}`).catch(() => {});
ws.close();

const result = {
  booted: !!state.booted,
  boot_ms: state.ms || null,
  serial_bytes: serial.length,
  screenshot: `${OUT}/boot.png`,
  serial_log: `${OUT}/serial.log`,
};
console.log("RESULT " + JSON.stringify(result));
process.exit(result.booted ? 0 : 2);
