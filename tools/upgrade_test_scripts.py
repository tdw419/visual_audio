import os, glob

for file in glob.glob("tools/test_*.py"):
    with open(file, 'r') as f:
        code = f.read()

    # Replace pc layout
    code = code.replace("('pc', np.uint32),", "('pc', np.uint32, 2),")
    # Replace regs layout
    code = code.replace("('regs', np.uint32, 32),", "('regs', np.uint32, (32, 2)),")
    
    # We might also need to update cpu_state[0]['pc'] assignments if they are 0.
    # We leave that for manual fix if necessary, or let numpy broadcast it. (cpu_state[0]['pc'] = [0, 0] or numpy handles it).

    with open(file, 'w') as f:
        f.write(code)
