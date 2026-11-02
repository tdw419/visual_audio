#!/usr/bin/env python3
"""
Render a live "pixel motherboard" visualization of the GPU RISC-V emulator.

This creates a real-time view showing:
- CPU core state (PC, registers, mode)
- Memory layout with heatmap of recent activity
- Page table walk visualization
- TLB cache state
- UART/network I/O buffers

Usage:
    python3 tools/pixel_motherboard.py [--heatmap] [--pt-walk]
"""
import sys
import os
import struct
import numpy as np
import curses
from collections import deque
import sqlite3
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE
from spatial_rv64i_cpu import SpatialRV64ICore

# Symbol DB for PC resolution
SYMBOL_DB = Path(__file__).parent.parent / "boot_images" / "alpine_riscv64_semantic.db"

def resolve_pc(pc: int) -> str:
    """Resolve a PC to a symbol name."""
    try:
        conn = sqlite3.connect(str(SYMBOL_DB))
        cursor = conn.cursor()
        signed_pc = pc - (1 << 64) if pc >= (1 << 63) else pc
        cursor.execute("""
            SELECT name, addr FROM kernel_symbols 
            WHERE addr <= ? ORDER BY addr DESC LIMIT 1
        """, (signed_pc,))
        result = cursor.fetchone()
        conn.close()
        if result:
            name, sym_addr = result
            offset = pc - (sym_addr + (1 << 64) if sym_addr < 0 else sym_addr)
            return f"{name}+0x{offset:x}"
        return "<unknown>"
    except:
        return "<error>"

def linearize_gpu_memory(core):
    """De-Hilbert-map GPU memory to linear bytes."""
    memory_spatial = core.queue.read_buffer(core.memory.buffer)
    spatial = np.frombuffer(memory_spatial, dtype=np.uint32)
    linear_words = spatial[core.hilbert_lut_np]
    return linear_words.tobytes()

class ActivityHeatmap:
    """Track memory access patterns over time."""
    def __init__(self, size_mb=64):
        # Divide RAM into 4KB pages for tracking
        self.page_size = 4096
        self.num_pages = (size_mb * 1024 * 1024) // self.page_size
        self.reads = np.zeros(self.num_pages, dtype=np.uint32)
        self.writes = np.zeros(self.num_pages, dtype=np.uint32)
        self.last_access_time = np.zeros(self.num_pages, dtype=np.float64)
        
    def record_access(self, addr, is_write, timestamp):
        """Record a memory access."""
        if addr >= 0x80000000:
            page_num = (addr - 0x80000000) // self.page_size
            if 0 <= page_num < self.num_pages:
                if is_write:
                    self.writes[page_num] += 1
                else:
                    self.reads[page_num] += 1
                self.last_access_time[page_num] = timestamp
    
    def get_heatmap_pixel(self, page_num):
        """Get a color pixel for a page based on activity."""
        # Calculate activity score (reads + 2*writes for visual weight)
        score = self.reads[page_num] + (self.writes[page_num] * 2)
        max_score = max(score, 1)  # Avoid div/0
        
        # Normalize to 0-255
        intensity = min(255, int((score / 256) * 255))
        
        # Blue = reads, Green = writes, mix for both
        r = 0
        g = min(255, self.writes[page_num] * 4)
        b = min(255, self.reads[page_num] * 4)
        
        # Decay old activity
        if self.reads[page_num] > 0:
            self.reads[page_num] = int(self.reads[page_num] * 0.99)
        if self.writes[page_num] > 0:
            self.writes[page_num] = int(self.writes[page_num] * 0.99)
        
        return (r, g, b)

class MotherboardView:
    """Render the motherboard visualization using curses."""
    
    def __init__(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)  # Hide cursor
        self.stdscr.nodelay(1)  # Non-blocking input
        self.stdscr.timeout(100)  # Refresh every 100ms
        
        self.heatmap = ActivityHeatmap()
        self.show_heatmap = True
        self.show_pt_walk = True
        self.highlight_va = 0x2ada15603d  # Faulting address from EFAULT
        
    def draw_box(self, y, x, height, width, title, content):
        """Draw a labeled box with content."""
        # Draw border
        self.stdscr.addch(y, x, '+')
        self.stdscr.addch(y, x + width - 1, '+')
        self.stdscr.addch(y + height - 1, x, '+')
        self.stdscr.addch(y + height - 1, x + width - 1, '+')
        
        for i in range(x + 1, x + width - 1):
            self.stdscr.addch(y, i, '-')
            self.stdscr.addch(y + height - 1, i, '-')
        
        for i in range(y + 1, y + height - 1):
            self.stdscr.addch(i, x, '|')
            self.stdscr.addch(i, x + width - 1, '|')
        
        # Title
        if title:
            title_pos = x + 2
            self.stdscr.addstr(y, title_pos, title)
        
        # Content
        if content:
            for i, line in enumerate(content[:height - 3]):
                if y + 2 + i < y + height - 1:
                    self.stdscr.addstr(y + 2 + i, x + 2, line[:width - 4])
    
    def render_cpu_state(self, state, registers, row):
        """Render CPU core state."""
        pc = state['pc']
        mode = state['mode']
        mode_name = ['M', 'S', 'U'][mode] if mode < 3 else f'?{mode}'
        
        symbol = resolve_pc(pc)
        
        content = [
            f"PC: 0x{pc:016x} ({symbol})",
            f"Mode: {mode_name}",
            f"Halted: {bool(state['halted'])}",
            "",
            "Key Registers:",
            f"  ra (x1): 0x{registers[1]:016x}",
            f"  sp (x2): 0x{registers[2]:016x}",
            f"  gp (x3): 0x{registers[3]:016x}",
            f"  tp (x4): 0x{registers[4]:016x}",
            f"  t0 (x5): 0x{registers[5]:016x}",
        ]
        
        self.draw_box(row, 2, 12, 30, "RISC-V CPU CORE", content)
        
    def render_memory_view(self, core, row):
        """Render memory layout with heatmap."""
        if not self.show_heatmap:
            content = [
                "Heatmap disabled (press 'h' to enable)",
                "",
                "RAM: 64MB at 0x80000000",
                "Highlight: 0x{:08x}".format(self.highlight_va),
            ]
        else:
            # Show a small window of the heatmap
            highlight_page = (self.highlight_va - 0x80000000) // 4096
            
            content = [
                f"Memory Heatmap (RAM: 64MB)",
                f"Highlight VA: 0x{self.highlight_va:016x}",
                "",
                "Access patterns (last 30s):",
                "",
            ]
            
            # Show activity around highlight
            for offset in range(-2, 3):
                page = highlight_page + offset
                if 0 <= page < self.heatmap.num_pages:
                    r, g, b = self.heatmap.get_heatmap_pixel(page)
                    activity = f"R:{self.heatmap.reads[page]} W:{self.heatmap.writes[page]}"
                    marker = ">>> " if offset == 0 else "    "
                    content.append(f"{marker}Page {page:05d}: [{r:02x}{g:02x}{b:02x}] {activity}")
        
        self.draw_box(row, 35, 14, 40, "MEMORY", content)
    
    def render_page_table(self, core, satp, row):
        """Render page table state."""
        satp_ppn = satp & 0x3FFFFF
        
        # Check the highlighted VA
        vpn2 = (self.highlight_va >> 30) & 0x1FF
        vpn1 = (self.highlight_va >> 21) & 0x1FF
        vpn0 = (self.highlight_va >> 12) & 0x1FF
        
        linear_mem = linearize_gpu_memory(core)
        
        def read_pte(pa):
            if pa >= 0x80000000 and pa < 0x80000000 + len(linear_mem):
                offset = pa - 0x80000000
                if offset + 8 <= len(linear_mem):
                    return struct.unpack('<Q', linear_mem[offset:offset+8])[0]
            return None
        
        # Walk to the highlighted address
        root_pa = (satp_ppn << 12)
        l2_pte = read_pte(root_pa + (vpn2 << 3))
        
        content = [
            f"satp: 0x{satp:016x}",
            f"Root PPN: 0x{satp_ppn:06x}",
            "",
            f"Walk for VA 0x{self.highlight_va:016x}:",
            f"  VPN2=0x{vpn2:03x} VPN1=0x{vpn1:03x} VPN0=0x{vpn0:03x}",
            "",
        ]
        
        if l2_pte is None:
            content.append("L2: READ ERROR")
        elif not (l2_pte & 1):
            content.append(f"L2: UNMAPPED (0x{l2_pte:016x}) <<< FAULT!")
        else:
            v2 = l2_pte & 1
            r2 = (l2_pte >> 1) & 1
            w2 = (l2_pte >> 2) & 1
            x2 = (l2_pte >> 3) & 1
            ppn2 = l2_pte >> 10
            
            if r2 or x2:
                content.append(f"L2: LEAF V={v2} R={r2} W={w2} X={x2}")
            else:
                content.append(f"L2: V={v2} R={r2} W={w2} X={x2} → PPN=0x{ppn2:x}")
                
                l1_pte = read_pte((ppn2 << 12) + (vpn1 << 3))
                if l1_pte and (l1_pte & 1):
                    r1 = (l1_pte >> 1) & 1
                    w1 = (l1_pte >> 2) & 1
                    x1 = (l1_pte >> 3) & 1
                    ppn1 = l1_pte >> 10
                    
                    if r1 or x1:
                        content.append(f"L1: LEAF V=1 R={r1} W={w1} X={x1}")
                    else:
                        l0_pte = read_pte((ppn1 << 12) + (vpn0 << 3))
                        if l0_pte and (l0_pte & 1):
                            r0 = (l0_pte >> 1) & 1
                            w0 = (l0_pte >> 2) & 1
                            x0 = (l0_pte >> 3) & 1
                            final_ppn = l0_pte >> 10
                            content.append(f"L0: MAPPED V=1 R={r0} W={w0} X={x0}")
                            content.append(f"    → PA 0x{(final_ppn << 12):08x}")
                        else:
                            content.append("L0: UNMAPPED <<< FAULT!")
        
        self.draw_box(row, 78, 14, 40, "PAGE TABLE WALK", content)
    
    def render_status(self, steps, uart_len, row):
        """Render overall status."""
        content = [
            f"Steps: {steps:,}",
            f"UART buffer: {uart_len} bytes",
            "",
            "Press 'q' to quit",
            "Press 'h' to toggle heatmap",
            "Press 'p' to toggle PT walk",
        ]
        
        self.draw_box(row, 120, 10, 25, "STATUS", content)
    
    def refresh(self, core, state, registers, satp, steps):
        """Refresh the entire display."""
        self.stdscr.clear()
        
        # Top banner
        self.stdscr.addstr(0, 0, "=" * 160)
        self.stdscr.addstr(1, 65, "PIXEL MOTHERBOARD - GPU RISC-V EMULATOR")
        self.stdscr.addstr(2, 0, "=" * 160)
        
        # Render components
        self.render_cpu_state(state, registers, 4)
        self.render_memory_view(core, 4)
        self.render_page_table(core, satp, 4)
        
        uart_len = len(core.read_uart_output())
        self.render_status(steps, uart_len, 4)
        
        # Bottom status
        self.stdscr.addstr(17, 0, "=" * 160)
        
        self.stdscr.refresh()

def main(stdscr):
    view = MotherboardView(stdscr)
    
    print('[1] Initializing GPU core...')
    core = SpatialRV64ICore(RAM_SIZE)
    
    print('[2] Loading boot components...')
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    
    print('[3] Setting boot registers...')
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)
    
    print('[4] Starting motherboard view (press Ctrl+C to exit)...')
    
    steps = 0
    batch_size = 100_000
    last_refresh = 0
    
    try:
        while True:
            # Step the emulator
            core.step(steps=batch_size)
            steps += batch_size
            
            # Refresh display every 1M steps
            if steps - last_refresh >= 1_000_000:
                state = core.get_state()
                registers = core.queue.read_buffer(core.registers.buffer)
                satp = core.read_csr(0x180)
                
                view.refresh(core, state, registers, satp, steps)
                
                # Record heatmap activity (simplified - just sampling)
                if view.heatmap:
                    import time
                    view.heatmap.record_access(state['pc'], False, time.time())
                
                last_refresh = steps
            
            # Check for user input
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('h'):
                view.show_heatmap = not view.show_heatmap
            elif key == ord('p'):
                view.show_pt_walk = not view.show_pt_walk
                
    except KeyboardInterrupt:
        pass
    finally:
        curses.endwin()
        print(f"\nMotherboard view closed at {steps:,} steps")

if __name__ == '__main__':
    curses.wrapper(main)