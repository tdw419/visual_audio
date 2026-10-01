#!/usr/bin/env python3
import asyncio
import json
import numpy as np
import websockets
from cpu_emulator import PixelCPU
from assembler import assemble
from pathlib import Path

class VisualCPUServer:
    def __init__(self, rom_path: str, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.rom_path = Path(rom_path)
        self.cpu = PixelCPU(256, 256)
        self.cpu.load_program(self.rom_path)
        self.is_running = False
        self.cycles_per_frame = 4
        self.clients = set()
        self.breakpoints = {}
        self.hit_breakpoint_info = None

    def check_breakpoints(self) -> dict | None:
        pc_coord = (self.cpu.pc[0], self.cpu.pc[1])
        if 'pc' in self.breakpoints.get(pc_coord, set()):
            return {"type": "pc", "coord": list(pc_coord)}
        for r_coord in getattr(self.cpu, 'last_reads', []):
            if 'read' in self.breakpoints.get(tuple(r_coord), set()):
                return {"type": "read", "coord": list(r_coord)}
        for w_coord in getattr(self.cpu, 'last_writes', []):
            if 'write' in self.breakpoints.get(tuple(w_coord), set()):
                return {"type": "write", "coord": list(w_coord)}
        return None

    def step_with_breakpoints(self) -> bool:
        if self.cpu.step():
            return False # halted
        bp_hit = self.check_breakpoints()
        if bp_hit:
            self.is_running = False
            self.hit_breakpoint_info = bp_hit
            return False
        return True

    async def broadcast_state(self, batch_reads=None, batch_writes=None):
        if not self.clients:
            return
        
        meta = json.dumps({
            "cycle": self.cpu.cycle,
            "pc": [self.cpu.pc[0], self.cpu.pc[1]],
            "acc": int(self.cpu.accumulator),
            "zf": int(self.cpu.zero_flag),
            "halted": bool(self.cpu.halt_flag),
            "reads": batch_reads or [],
            "writes": batch_writes or [],
            "hit_breakpoint": self.hit_breakpoint_info,
            "breakpoints": [
                {"x": x, "y": y, "types": list(types)}
                for (x, y), types in self.breakpoints.items()
            ]
        }).encode('utf-8')
        
        self.hit_breakpoint_info = None
        
        meta_len = len(meta).to_bytes(4, byteorder='little')
        raw_pixels = self.cpu.memory.astype(np.uint8).tobytes()
        payload = meta_len + meta + raw_pixels

        await asyncio.gather(
            *[client.send(payload) for client in self.clients],
            return_exceptions=True
        )

    async def execution_loop(self):
        while True:
            if self.is_running and not self.cpu.halt_flag:
                batch_reads = []
                batch_writes = []
                for _ in range(self.cycles_per_frame):
                    if not self.step_with_breakpoints():
                        break
                    batch_reads.extend(self.cpu.last_reads)
                    batch_writes.extend(self.cpu.last_writes)
                await self.broadcast_state(batch_reads, batch_writes)
            await asyncio.sleep(0.016)

    async def handle_client(self, websocket):
        self.clients.add(websocket)
        await self.broadcast_state()
        try:
            async for message in websocket:
                cmd = json.loads(message)
                action = cmd.get("action")
                
                if action == "play":
                    self.is_running = True
                elif action == "pause":
                    self.is_running = False
                elif action == "step":
                    self.is_running = False
                    self.cpu.step()
                    await self.broadcast_state()
                elif action == "set_speed":
                    self.cycles_per_frame = max(1, int(cmd.get("cycles", 1)))
                elif action == "reset":
                    self.cpu = PixelCPU(256, 256)
                    self.cpu.load_program(self.rom_path)
                    self.is_running = False
                    await self.broadcast_state()
                elif action == "toggle_bp":
                    coord = (int(cmd["x"]), int(cmd["y"]))
                    bp_type = cmd.get("type", "write")
                    if coord not in self.breakpoints:
                        self.breakpoints[coord] = set()
                    if bp_type in self.breakpoints[coord]:
                        self.breakpoints[coord].remove(bp_type)
                        if not self.breakpoints[coord]:
                            del self.breakpoints[coord]
                    else:
                        self.breakpoints[coord].add(bp_type)
                    await self.broadcast_state()
                elif action == "clear_all_bp":
                    self.breakpoints.clear()
                    await self.broadcast_state()
                elif action == "interrupt":
                    irq = int(cmd.get("irq", 1))
                    x = int(cmd.get("x", 0))
                    y = int(cmd.get("y", 0))
                    self.cpu.raise_interrupt(irq, x, y)
                    if not self.is_running:
                        # let the CPU service it immediately even while paused
                        self.cpu.step()
                        await self.broadcast_state()
                elif action == "write_text":
                    text = cmd.get("text", "")
                    lexer_entry_x = int(cmd.get("entry_x", 0))
                    lexer_entry_y = int(cmd.get("entry_y", 1)) # Coordinate of ascii_lexer boot
                    
                    # 1. Clear ASCII buffer at y=220
                    self.cpu.memory[220, :, :] = 0
                    
                    # 2. Write raw ASCII bytes + null terminator into row y=220
                    for idx, ch in enumerate(text.encode('ascii', errors='ignore')[:255]):
                        self.cpu.memory[220, idx] = [ch, 0, 0, 255]
                        self.access_log.append([1, idx, 220])
                    self.cpu.memory[220, len(text)] = [0, 0, 0, 255] # Null terminator

                    # 3. Vector CPU directly to the In-Pixel Lexer
                    self.cpu.pc = (lexer_entry_x, lexer_entry_y)
                    self.cpu.accumulator = 0
                    self.cpu.zero_flag = 0
                    self.cpu.halt_flag = 0
                    
                    # Ensure sp exists, default to 16
                    # Wait, our emulator doesn't have SP explicitly exposed as attribute, it is in memory!
                    # Reset memory state
                    self.cpu.memory[0, 15] = [16, 0, 0, 255] # SP = 16

                    self.is_running = True
                    print(f"[⌨] Injected {len(text)} bytes ASCII into y=220. Booting lexer at ({lexer_entry_x}, {lexer_entry_y})")
                    await self.broadcast_state()
        finally:
            self.clients.remove(websocket)

    async def run(self):
        async with websockets.serve(self.handle_client, self.host, self.port):
            print(f"[*] Visual Shell Server listening on ws://{self.host}:{self.port}")
            await self.execution_loop()

if __name__ == "__main__":
    import sys
    rom = sys.argv[1] if len(sys.argv) > 1 else "conway_working.png"
    server = VisualCPUServer(rom)
    asyncio.run(server.run())
