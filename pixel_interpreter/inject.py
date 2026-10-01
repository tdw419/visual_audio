#!/usr/bin/env python3
"""
CLI tool to inject .glyph code directly into the live Pixel Interpreter over WebSockets.
Usage:
    python3 inject.py my_code.glyph
    python3 inject.py -s "SET 42\nSTORE (0, 128)\nHALT"
"""

import sys
import asyncio
import json
import argparse
import websockets

async def inject_code(source: str, host: str, port: int, reset_pc: bool):
    uri = f"ws://{host}:{port}"
    try:
        async with websockets.connect(uri) as ws:
            # Send injection payload
            payload = {
                "action": "inject_glyph",
                "source": source,
                "reset_pc": reset_pc
            }
            await ws.send(json.dumps(payload))
            
            # Wait for server response
            resp_raw = await ws.recv()
            if isinstance(resp_raw, bytes):
                # Server sent a state frame, read next text frame or decode ack
                print("✓ Injected into running VM (binary frame received).")
            else:
                resp = json.loads(resp_raw)
                if resp.get("status") == "ok":
                    print(f"✓ Successfully injected into live VM at cycle {resp.get('cycle', 0)}.")
                else:
                    print(f"✗ Server error: {resp.get('message')}")
    except ConnectionRefusedError:
        print(f"✗ Could not connect to Pixel CPU server at {uri}. Is cpu_server.py running?")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Inject .glyph source directly into live Pixel CPU.")
    parser.add_argument("file", nargs="?", help="Path to .glyph file")
    parser.add_argument("-s", "--source", help="Raw inline .glyph string")
    parser.add_argument("--host", default="localhost", help="WebSocket host (default: localhost)")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket port (default: 8765)")
    parser.add_argument("--no-reset", action="store_true", help="Do not reset PC/ACC on inject")
    
    args = parser.parse_args()
    
    if args.source:
        glyph_source = args.source
    elif args.file:
        with open(args.file, "r") as f:
            glyph_source = f.read()
    else:
        # Read from STDIN (pipe friendly)
        glyph_source = sys.stdin.read()
        
    if not glyph_source.strip():
        print("✗ Empty source provided.")
        sys.exit(1)

    asyncio.run(inject_code(glyph_source, args.host, args.port, not args.no_reset))

if __name__ == "__main__":
    main()
