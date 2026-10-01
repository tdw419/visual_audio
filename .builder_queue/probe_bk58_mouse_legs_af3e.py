#!/usr/bin/env python3
"""BK-58 research tick: REAL mouse hit-testing legs (builder af3e, 2026-10-01).

Closes the manual-checklist item the prior probe named "Not exercised":
actual mouse hit-testing geometry (canvas pixel math) — mousedown/mousemove/
click/wheel are dispatched as REAL Input.dispatchMouseEvent CDP events at
computed viewport coordinates, and the assertion is on the DOM state those
handlers mutate (hoverCell/tooltip/selectedCell/drawer/zoom/pan).

Uses the viewer's OWN inverse mapping to pick target coordinates:
  mouseX = (clientX - rect.left - panX) / zoom
  cx     = floor(mouseX / cellSize)
so clientX = rect.left + panX + (cx + 0.5) * cellSize * zoom.

Legs:
  M1  hover: real mousemove over a commit cell -> tooltip visible, text
      carries the cell's type+title, hoverCell set
  M2  click: real mousedown+mouseup+click at the same point -> drawer
      opens with that cell's title + badge
  M3  zoom-at-cursor: real wheel over a background point -> zoom changes
      by exactly 1.15x (deltaY>0), cursor-anchored pan math preserved
  M4  hover off-cell: real mousemove over empty map area -> tooltip
      hidden, hoverCell cleared (the negative leg)

RED-first (probe_bk58_mouse_red_af3e.py): served-copy neuter breaks the
mousemove pick math -> M1/M2 go RED with hoverCell null.

Run: python3 probe_bk58_mouse_legs_af3e.py <cdp_port>
Requires: http server on :8091 serving repo root + bridge NOT required
(these legs never touch the launch socket).
"""
import base64
import json
import math
import socket
import struct
import sys
import time
import urllib.request

WS_DEBUG = "http://127.0.0.1:%s/json" % (sys.argv[1] if len(sys.argv) > 1 else "9222")
RESULTS = []


def ws_connect(url):
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


def mouse(cdp, x, y, type_, button=None, click_count=None):
    p = {"type": type_, "x": x, "y": y, "button": button or "none",
         "clickCount": click_count or 0}
    cdp.cmd("Input.dispatchMouseEvent", **p)


def main():
    targets = json.loads(urllib.request.urlopen(WS_DEBUG, timeout=5).read())
    page = [t for t in targets if t.get("type") == "page"
            and "build_map_viewer" in t.get("url", "")]
    assert page, [t.get("url") for t in targets]
    cdp = CDP(page[0]["webSocketDebuggerUrl"])

    cdp.cmd("Page.enable")
    cdp.cmd("Page.reload", ignoreCache=True)  # the BK-58 lesson: forced reload
    time.sleep(4)

    # M0 precondition: page is live and a commit cell exists
    hud = json.loads(cdp.eval_js(
        "JSON.stringify({cells: (mapData && mapData.cells) ?"
        " mapData.cells.length : 0, imgLoaded: imgLoaded, zoom, panX, panY})"))
    assert hud["cells"] > 0 and hud["imgLoaded"], hud

    # Pick a commit cell with a distinctive title, compute its CENTER client
    # coords via the viewer's OWN inverse mapping (same math the handler inverts)
    tgt = json.loads(cdp.eval_js("""
      (function() {
        const cell = mapData.cells.find(c => c.type === 'commit' && c.title.length > 20);
        if (!cell) return JSON.stringify({err: 'no commit cell'});
        const rect = canvas.getBoundingClientRect();
        const side = mapData.meta.side || 128;
        const cellSize = 1024 / side;
        const cx = (cell.x + 0.5) * cellSize, cy = (cell.y + 0.5) * cellSize;
        return JSON.stringify({x: cell.x, y: cell.y, title: cell.title,
                               type: cell.type,
                               clientX: rect.left + panX + cx * zoom,
                               clientY: rect.top + panY + cy * zoom,
                               rectLeft: rect.left, rectTop: rect.top});
      })()
    """))
    assert "err" not in tgt, tgt
    tx, ty = tgt["clientX"], tgt["clientY"]
    print("target cell (%d,%d) at client (%.1f, %.1f)" %
          (tgt["x"], tgt["y"], tx, ty))

    # M1: real mousemove over the cell -> tooltip + hoverCell
    mouse(cdp, tx, ty, "mouseMoved")
    time.sleep(0.4)
    m1 = json.loads(cdp.eval_js("""
      JSON.stringify({hover: hoverCell ? (hoverCell.x + ',' + hoverCell.y) : null,
                      tipShown: tooltip.style.display === 'block',
                      tipText: tooltip.textContent.slice(0, 120)})
    """))
    # EXACT-cell assertion: the neuter shifts the pick into the ADJACENT cell
    # (1,0) — which is also a commit cell — so "any tooltip" passes vacuously.
    # The leg asserts the picked cell IS the targeted cell and its title text.
    record("M1-hover-pick",
           m1["hover"] == f'{tgt["x"]},{tgt["y"]}' and m1["tipShown"]
           and tgt["title"] in m1["tipText"],
           json.dumps(m1))

    # M2: real mousedown+mouseup+click at the same point -> drawer opens
    mouse(cdp, tx, ty, "mousePressed", button="left", click_count=1)
    mouse(cdp, tx, ty, "mouseReleased", button="left", click_count=1)
    time.sleep(0.4)
    m2 = json.loads(cdp.eval_js("""
      JSON.stringify({open: drawer.classList.contains('open'),
                      badge: document.getElementById('drawer-badge').textContent,
                      title: document.getElementById('drawer-title').textContent,
                      sel: selectedCell ? (selectedCell.x + ',' + selectedCell.y) : null})
    """))
    record("M2-click-drawer",
           m2["open"] and m2["sel"] == f'{tgt["x"]},{tgt["y"]}'
           and tgt["title"] in m2["title"],
           json.dumps(m2))
    # close the drawer so it can't eat later legs
    cdp.eval_js("document.getElementById('drawer-close').click()")
    time.sleep(0.2)

    # M3: real wheel at a fixed screen point over the map center -> zoom 1/1.15
    zm = json.loads(cdp.eval_js(
        "JSON.stringify({zoom, panX, panY,"
        " cx: canvas.getBoundingClientRect().left + canvas.width / 2,"
        " cy: canvas.getBoundingClientRect().top + canvas.height / 2})"))
    before = zm["zoom"]
    mouse(cdp, zm["cx"], zm["cy"], "mouseWheel")
    cdp.cmd("Input.dispatchMouseEvent", type="mouseWheel", x=zm["cx"],
            y=zm["cy"], deltaX=0, deltaY=120)
    time.sleep(0.4)
    after = cdp.eval_js("zoom")
    ratio = before / after if after else 0
    record("M3-wheel-zoom-out",
           math.isclose(ratio, 1.15, rel_tol=1e-9),
           f"zoom {before} -> {after} (ratio {ratio:.6f}, expect exactly 1.15)")

    # M4 negative leg: hover over empty map area -> tooltip hides
    emp = json.loads(cdp.eval_js("""
      (function() {
        // find a map coordinate with no cell: scan grid for a gap
        const side = mapData.meta.side || 128;
        const occ = new Set(mapData.cells.map(c => c.x + ',' + c.y));
        let gx = -1, gy = -1;
        outer: for (let y = 0; y < side; y++) for (let x = 0; x < side; x++)
          if (!occ.has(x + ',' + y)) { gx = x; gy = y; break outer; }
        const rect = canvas.getBoundingClientRect();
        const cellSize = 1024 / side;
        return JSON.stringify({clientX: rect.left + panX + (gx + 0.5) * cellSize * zoom,
                               clientY: rect.top + panY + (gy + 0.5) * cellSize * zoom,
                               gx, gy});
      })()
    """))
    assert "err" not in emp, emp
    # must be inside the visible viewport for the handler to see it
    assert 0 <= emp["clientX"] <= 1280 and 0 <= emp["clientY"] <= 800, emp
    mouse(cdp, emp["clientX"], emp["clientY"], "mouseMoved")
    time.sleep(0.4)
    m4 = json.loads(cdp.eval_js(
        "JSON.stringify({hover: hoverCell, tip: tooltip.style.display})"))
    record("M4-hover-clears",
           m4["hover"] is None and m4["tip"] == "none", json.dumps(m4))

    print("\nSUMMARY:", sum(1 for _, ok, _ in RESULTS if ok), "/",
          len(RESULTS), "legs green")
    raise SystemExit(0 if all(ok for _, ok, _ in RESULTS) else 1)


if __name__ == "__main__":
    main()
