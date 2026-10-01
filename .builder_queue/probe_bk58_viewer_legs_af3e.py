#!/usr/bin/env python3
"""BK-58 manual-checklist headless-browser legs (builder af3e, 2026-10-01).

Drives the REAL viewer HTML (tools/build_map_viewer.html copy served over
http://127.0.0.1:8091) in headless Chromium via the DevTools protocol
(websocket-client, stdlib otherwise), against the REAL bridge on :8766.

Legs (from the BK-58 landing's manual-checklist, PRODUCT_LANE_STATE.md:7):
  V1  page loads, map data fetched, HUD populated (no JS errors fatal)
  V2  drawer opens on cell selection; Run button visible for a launch-class
      cell; terminal pane + input shown after connect click
  V3  a real glyphdbg send over the viewer's WebSocket path returns output
      rendered into the term pane (textContent path, termLine)
  V4  ollama-class verdict cell routes prompt to the bridge (accepted or
      refused by availability — either way the WS round trip happened)
Not exercised: actual mouse hit-testing geometry (canvas pixel math) —
driven programmatically at the same functions the click handlers call.

Run: python3 bk58_viewer_legs.py   (needs bridge :8766 + http :8091)
"""
import base64
import json
import socket
import struct
import time
import urllib.request

WS_DEBUG = ("http://127.0.0.1:9222/json")
import sys
if len(sys.argv) > 1:
    WS_DEBUG = "http://127.0.0.1:%s/json" % sys.argv[1]
RESULTS = []


def ws_connect(url):
    """Minimal ws client: returns (sock, send, recv) closures."""
    import urllib.parse
    u = urllib.parse.urlparse(url)
    s = socket.create_connection((u.hostname, u.port), timeout=10)
    key = base64.b64encode(b"0123456789abcdef").decode()
    req = (f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    s.sendall(req.encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        buf += s.recv(4096)
    assert b"101" in buf.split(b"\r\n")[0], buf[:100]

    def send(payload):
        data = payload.encode()
        mask = b"\x11\x22\x33\x44"
        n = len(data)
        if n < 126:
            hdr = bytes([0x81, 0x80 | n])
        else:
            hdr = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
        s.sendall(hdr + mask + bytes(b ^ mask[i % 4]
                                     for i, b in enumerate(data)))

    def recv():
        hdr = s.recv(2)
        while len(hdr) < 2:
            hdr += s.recv(2 - len(hdr))
        n = hdr[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", s.recv(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", s.recv(8))[0]
        data = b""
        while len(data) < n:
            data += s.recv(n - len(data))
        return data.decode()

    return s, send, recv


class CDP:
    def __init__(self, ws_url):
        self.sock, self.send, self.recv = ws_connect(ws_url)
        self.mid = 0

    def cmd(self, method, **params):
        self.mid += 1
        self.send(json.dumps({"id": self.mid, "method": method,
                              "params": params}))
        while True:
            msg = json.loads(self.recv())
            if msg.get("id") == self.mid:
                return msg

    def eval_js(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr,
                     returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("result", {}).get("value")


def record(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), name, "-", detail)


def main():
    # find the page target on the debug port
    targets = json.loads(urllib.request.urlopen(WS_DEBUG, timeout=5).read())
    page = [t for t in targets if t.get("type") == "page"
            and "build_map_viewer" in t.get("url", "")]
    assert page, [t.get("url") for t in targets]
    cdp = CDP(page[0]["webSocketDebuggerUrl"])

    # force a real reload so the CURRENTLY SERVED html is what's running
    cdp.cmd("Page.enable")
    cdp.cmd("Page.reload", ignoreCache=True)
    time.sleep(4)

    # V1: HUD populated, no fatal error banner in console
    hud = cdp.eval_js(
        "JSON.stringify({commits: document.getElementById('cnt-commits')"
        ".textContent, pct: document.getElementById('pct-claimed')"
        ".textContent, frontier: document.getElementById('frontier-info')"
        ".textContent, cells: (mapData && mapData.cells) ?"
        " mapData.cells.length : 0, imgLoaded: imgLoaded})")
    hud = json.loads(hud)
    record("V1-hud", hud["cells"] > 0 and hud["imgLoaded"] is True and
           hud["commits"] not in ("-", "", None), json.dumps(hud))

    # V2: select a launch-class cell programmatically (same entry the click
    # handler uses), drawer opens, Run button visible, then termConnect
    v2 = cdp.eval_js("""
      (function() {
        const cell = mapData.cells.find(c => launchClassFor(c) === 'glyphdbg');
        if (!cell) return JSON.stringify({err: 'no glyphdbg cell'});
        selectedCell = cell;
        openDrawer(cell);
        const drawerOpen = drawer.classList.contains('open');
        const btnVisible = document.getElementById('drawer-run')
                            .style.display === 'block';
        const btnText = document.getElementById('drawer-run').textContent;
        return JSON.stringify({drawerOpen, btnVisible, btnText,
                               cell: cell.x + ',' + cell.y,
                               cls: launchClassFor(cell)});
      })()
    """)
    v2 = json.loads(v2)
    record("V2-drawer", v2.get("drawerOpen") and v2.get("btnVisible"),
           json.dumps(v2))

    # connect (the Run button's action)
    cdp.eval_js("document.getElementById('drawer-run').click()")
    time.sleep(1.0)
    state = json.loads(cdp.eval_js(
        "JSON.stringify({open: termOpen, ready: termSock ?"
        " termSock.readyState : -1, termShown: document.getElementById('term')"
        ".style.display, lines: document.getElementById('term')"
        ".childElementCount})"))
    record("V2b-term-connect", state["open"] and state["ready"] == 1
           and state["termShown"] == "block", json.dumps(state))

    # V3: send a glyphdbg program the way termSend does. termSend sends
    # async; poll for a NEW term line whose text is the program output.
    baseline = cdp.eval_js(
        "document.getElementById('term').childElementCount")
    cdp.eval_js("termSend('LDI r7 7\\nPRT r7\\nHALT')")
    term_text = ""
    for _ in range(20):
        time.sleep(0.5)
        n_now = cdp.eval_js(
            "document.getElementById('term').childElementCount")
        if n_now > baseline:
            term_text = cdp.eval_js(
                "Array.from(document.getElementById('term').children)"
                ".slice(-1).map(d => d.textContent).join('\\n')")
            if term_text.strip():
                break
    record("V3-glyphdbg-output", "7" in term_text and "λ" not in term_text,
           repr(term_text[-200:]))

    # V4: verdict cell -> ollama class routing (availability-agnostic)
    v4 = cdp.eval_js("""
      (function() {
        const cell = mapData.cells.find(c => launchClassFor(c) === 'ollama');
        if (!cell) return JSON.stringify({err: 'no ollama cell'});
        selectedCell = cell;
        openDrawer(cell);
        return JSON.stringify({btn: document.getElementById('drawer-run')
          .textContent});
      })()
    """)
    v4 = json.loads(v4)
    baseline = cdp.eval_js(
        "document.getElementById('term').childElementCount")
    cdp.eval_js("termSend('reply with the single word: pong')")
    term_text = ""
    for _ in range(80):
        time.sleep(0.5)
        n_now = cdp.eval_js(
            "document.getElementById('term').childElementCount")
        if n_now > baseline:
            term_text = cdp.eval_js(
                "Array.from(document.getElementById('term').children)"
                ".slice(-1).map(d => d.textContent).join('\\n')")
            break
    routed = ("pong" in term_text.lower()) or ("unreachable" in term_text)
    record("V4-ollama-route", routed and "ollama" in v4.get("btn", ""),
           repr(term_text[-200:]))

    cdp.cmd("Page.close") if False else None
    print("\nSUMMARY:", sum(1 for _, ok, _ in RESULTS if ok), "/",
          len(RESULTS), "legs green")
    raise SystemExit(0 if all(ok for _, ok, _ in RESULTS) else 1)


if __name__ == "__main__":
    main()
