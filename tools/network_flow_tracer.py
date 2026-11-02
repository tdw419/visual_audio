#!/usr/bin/env python3
"""
Network flow tracer - visualizes data passing through the pixel motherboard.

Tracks HTTP/HTTPS requests through the entire stack:
  User input → Application → Kernel → VirtIO → Network card

Usage:
    python3 tools/network_flow_tracer.py [--verbose]
"""
import sys
import os
import struct
import re
from collections import deque, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE
from spatial_rv64i_cpu import SpatialRV64ICore

# HTTP patterns to detect
HTTP_PATTERNS = [
    rb'GET\s+/\s+HTTP/1',
    rb'POST\s+/\s+HTTP/1',
    rb'HTTP/1\.[01]\s+\d{3}',
    rb'Host:\s+',
    rb'User-Agent:\s+',
]

# Network-related memory regions (RISC-V virtio)
VIRTIO_NET_RX_QUEUE = 0x10001000
VIRTIO_NET_TX_QUEUE = 0x10001020
VIRTIO_NET_CFG = 0x10001040

class NetworkPacket:
    """Represents a network packet with metadata."""
    def __init__(self, direction, data, timestamp, pc):
        self.direction = direction  # 'tx' or 'rx'
        self.data = data
        self.timestamp = timestamp
        self.pc = pc
        self.analyzed = False
        self.protocol = 'unknown'
        self.summary = ''
    
    def analyze(self):
        """Try to identify protocol and extract summary."""
        data_str = self.data.decode('latin-1', errors='replace')
        
        # Check for HTTP
        if any(pattern in self.data for pattern in HTTP_PATTERNS):
            self.protocol = 'HTTP'
            lines = data_str.split('\r\n')[:5]
            self.summary = lines[0] if lines else data_str[:50]
            return
        
        # Check for TCP/UDP
        if len(self.data) >= 20:  # IP header minimum
            version = (self.data[0] >> 4) & 0xF
            if version == 4:
                protocol = self.data[9]
                if protocol == 6:  # TCP
                    self.protocol = 'TCP'
                    src_port = (self.data[0] << 8) | self.data[1]
                    dst_port = (self.data[2] << 8) | self.data[3]
                    self.summary = f'TCP {src_port} → {dst_port}'
                elif protocol == 17:  # UDP
                    self.protocol = 'UDP'
                    self.summary = f'UDP packet'
        
        if not self.summary:
            self.summary = f'{len(self.data)} bytes'

class NetworkFlowTracer:
    """Traces network data flow through the emulator."""
    
    def __init__(self, core):
        self.core = core
        self.packets = deque(maxlen=100)
        self.memory_watches = defaultdict(list)
        self.last_memory_state = {}
        
        # Watch for HTTP data in user space
        self.http_watches = []
        
        # VirtIO network region
        self.virtio_region_start = VIRTIO_NET_CFG
        self.virtio_region_end = VIRTIO_NET_CFG + 0x100
        
        # Buffer for recent UART output
        self.uart_buffer = deque(maxlen=5000)
        
    def scan_for_http(self, linear_mem):
        """Scan user space for HTTP-related strings."""
        # Scan last 1MB of RAM for HTTP patterns
        scan_end = len(linear_mem)
        scan_start = max(0, scan_end - 1024 * 1024)
        
        for pattern in HTTP_PATTERNS:
            offset = 0
            while True:
                idx = linear_mem.find(pattern, scan_start + offset, scan_end)
                if idx == -1:
                    break
                
                # Found HTTP data
                addr = 0x80000000 + idx
                self.http_watches.append({
                    'addr': addr,
                    'pattern': pattern.decode('latin-1', errors='ignore'),
                    'timestamp': self.steps
                })
                
                offset = idx + len(pattern)
                if offset > scan_end - scan_start:
                    break
    
    def check_virtio_activity(self, linear_mem):
        """Check for VirtIO network activity."""
        # Read virtio MMIO region
        virtio_data = linear_mem[
            self.virtio_region_start - 0x80000000:
            self.virtio_region_end - 0x80000000
        ]
        
        # Look for queue notifications
        # This is simplified - real VirtIO would parse the actual ring buffers
        activity = {
            'tx_queue_ready': False,
            'rx_queue_ready': False,
            'last_written': None
        }
        
        # Check if any values changed (activity)
        if hasattr(self, 'last_virtio_data'):
            for i, (old, new) in enumerate(zip(self.last_virtio_data, virtio_data)):
                if old != new:
                    addr = self.virtio_region_start + i
                    activity['last_written'] = addr
        
        self.last_virtio_data = virtio_data
        return activity
    
    def detect_memory_access_pattern(self, linear_mem):
        """Detect patterns suggesting data copy operations."""
        changes = []
        
        # Sample random locations for changes
        sample_addrs = [
            0x80800000,  # Kernel heap
            0x81000000,  # User space start
            0x82000000,  # Network buffers
        ]
        
        for addr in sample_addrs:
            offset = addr - 0x80000000
            if 0 <= offset < len(linear_mem) - 64:
                data = linear_mem[offset:offset+64]
                
                if addr in self.last_memory_state:
                    old = self.last_memory_state[addr]
                    if old != data:
                        changes.append({
                            'addr': addr,
                            'old_size': len(old),
                            'new_size': len(data),
                            'diff': True
                        })
                
                self.last_memory_state[addr] = data
        
        return changes
    
    def update(self, steps, state, linear_mem):
        """Update tracer state."""
        self.steps = steps
        
        # Check UART for network activity hints
        uart = self.core.read_uart_output()
        if uart:
            uart_str = uart.decode('latin-1', errors='replace')
            self.uart_buffer.extend(uart_str)
        
        # Check for HTTP data in memory
        self.scan_for_http(linear_mem)
        
        # Check VirtIO activity
        virtio_activity = self.check_virtio_activity(linear_mem)
        
        # Detect memory access patterns
        memory_changes = self.detect_memory_access_pattern(linear_mem)
        
        return {
            'http_watches': len(self.http_watches),
            'virtio_active': virtio_activity['last_written'] is not None,
            'memory_changes': len(memory_changes),
            'uart_messages': list(self.uart_buffer)[-5:]
        }
    
    def render_flow_diagram(self, status):
        """Render ASCII art of data flow."""
        diagram = []
        
        diagram.append("┌─────────────────────────────────────────────────┐")
        diagram.append("│              NETWORK DATA FLOW                   │")
        diagram.append("├─────────────────────────────────────────────────┤")
        
        # User input / application layer
        if 'http://' in '\n'.join(status['uart_messages']):
            diagram.append("│  [USER] ●●●● http request typed in terminal")
        else:
            diagram.append("│  [USER] waiting for input...")
        
        # Kernel layer
        diagram.append("│     │")
        diagram.append("│     ▼")
        
        if status['memory_changes'] > 0:
            diagram.append(f"│  [KERNEL] ●●● copy_to_user() ({status['memory_changes']} regions)")
        else:
            diagram.append("│  [KERNEL] idle")
        
        # VirtIO layer
        diagram.append("│     │")
        diagram.append("│     ▼")
        
        if status['virtio_active']:
            diagram.append("│  [VIRTIO] ●●● queue activity detected")
        else:
            diagram.append("│  [VIRTIO] no queue notifications")
        
        # Network card
        diagram.append("│     │")
        diagram.append("│     ▼")
        diagram.append("│  [NET] →→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→")
        
        diagram.append("└─────────────────────────────────────────────────┘")
        diagram.append("")
        diagram.append(f"HTTP detections in memory: {status['http_watches']}")
        diagram.append(f"Recent UART messages:")
        for msg in status['uart_messages'][-3:]:
            diagram.append(f"  > {msg.strip()[:60]}")
        
        return '\n'.join(diagram)

def main():
    print('[1] Initializing GPU core...')
    core = SpatialRV64ICore(RAM_SIZE)
    
    print('[2] Loading boot components...')
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    
    print('[3] Setting boot registers...')
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)
    
    print('[4] Initializing network flow tracer...')
    tracer = NetworkFlowTracer(core)
    
    print('[5] Starting boot with network tracing...')
    
    steps = 0
    batch_size = 500_000
    last_render = 0
    
    try:
        while steps < 2_000_000_000:
            core.step(steps=batch_size)
            steps += batch_size
            
            # Update tracer every 5M steps
            if steps - last_render >= 5_000_000:
                state = core.get_state()
                
                # Linearize memory for tracing
                import numpy as np
                memory_spatial = core.queue.read_buffer(core.memory.buffer)
                spatial = np.frombuffer(memory_spatial, dtype=np.uint32)
                linear_mem = spatial[core.hilbert_lut_np].tobytes()
                
                # Update tracer
                status = tracer.update(steps, state, linear_mem)
                
                # Render flow diagram
                if status['http_watches'] > 0 or status['virtio_active']:
                    diagram = tracer.render_flow_diagram(status)
                    print(f"\n{'='*60}")
                    print(f"STEPS: {steps:,}")
                    print(diagram)
                    print(f"{'='*60}\n")
                
                last_render = steps
                
            # Check for completion or errors
            uart = core.read_uart_output()
            if uart:
                uart_str = uart.decode('latin-1', errors='replace')
                if "couldn't execute" in uart_str or "Failed to execute" in uart_str:
                    print("\n[!!!] EFAULT detected - network trace stopped")
                    break
    
    except KeyboardInterrupt:
        print(f"\nNetwork trace stopped at {steps:,} steps")

if __name__ == '__main__':
    main()