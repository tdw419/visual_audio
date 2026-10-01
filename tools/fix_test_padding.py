import os, glob

for file in glob.glob("tools/test_*.py"):
    with open(file, 'r') as f:
        code = f.read()

    # Add padding to cpu_layout
    code = code.replace("('output_ptr', np.uint32),", "('output_ptr', np.uint32),\n        ('padding', np.uint32),")
    
    # We also need to fix checking of regs since we changed it to (32,2)
    # The tests probably do: final_cpu['regs'][10] == 0x00100100
    # Now it is final_cpu['regs'][10][0] == 0x00100100
    code = code.replace("final_cpu['regs'][0] ==", "final_cpu['regs'][0][0] ==")
    code = code.replace("final_cpu['regs'][1] ==", "final_cpu['regs'][1][0] ==")
    code = code.replace("final_cpu['regs'][10] ==", "final_cpu['regs'][10][0] ==")
    code = code.replace("final_cpu['regs'][11] ==", "final_cpu['regs'][11][0] ==")
    code = code.replace("final_cpu['regs'][12] ==", "final_cpu['regs'][12][0] ==")
    code = code.replace("final_cpu['regs'][13] ==", "final_cpu['regs'][13][0] ==")

    # Also for printing:
    code = code.replace("final_cpu['regs'][0]:08x", "final_cpu['regs'][0][0]:08x")
    code = code.replace("final_cpu['regs'][1]:08x", "final_cpu['regs'][1][0]:08x")
    code = code.replace("final_cpu['regs'][10]:08x", "final_cpu['regs'][10][0]:08x")
    code = code.replace("final_cpu['regs'][11]:08x", "final_cpu['regs'][11][0]:08x")
    code = code.replace("final_cpu['regs'][12]:08x", "final_cpu['regs'][12][0]:08x")
    code = code.replace("final_cpu['regs'][13]:08x", "final_cpu['regs'][13][0]:08x")
    
    # fix PC printing/checking
    code = code.replace("final_cpu['pc']:08x", "final_cpu['pc'][0]:08x")
    code = code.replace("cpu_readback[0]['pc']", "cpu_readback[0]['pc'][0]")

    with open(file, 'w') as f:
        f.write(code)
