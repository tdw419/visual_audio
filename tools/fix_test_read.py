import re

with open('tools/test_mmu_gpu.py', 'r') as f:
    code = f.read()

# Replace the complicated mapping with queue.read_buffer
code = re.sub(
    r'read_buf = device.create_buffer.*?cpu_readback = np.frombuffer\(read_buf.map_read\(\), dtype=cpu_layout\)',
    '''cpu_readback = np.frombuffer(device.queue.read_buffer(buf_cpu), dtype=cpu_layout)''',
    code, flags=re.DOTALL
)

with open('tools/test_mmu_gpu.py', 'w') as f:
    f.write(code)

