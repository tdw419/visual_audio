import numpy as np
import sys
from io import StringIO
from tools.spatial_rv32i_cpu import SpatialRV32ICore
from tools.rv32i_asm import assemble

def test_sbi_console_putchar():
    core = SpatialRV32ICore(1024 * 1024)

    # SBI Console Putchar:
    # a7 (x17) = 1
    # a0 (x10) = character (e.g. 72 for 'H')
    # ecall
    
    asm_source = """
    # Set up SBI Extension ID (Console Putchar = 1) in a7
    addi a7, zero, 1
    
    # Set up character 'H' (72) in a0
    addi a0, zero, 72
    ecall
    
    # Set up character 'i' (105) in a0
    addi a0, zero, 105
    ecall
    
    # Set up character '!' (33) in a0
    addi a0, zero, 33
    ecall
    
    # Halt by jumping to self
    halt:
    jal zero, halt
    """
    
    binary = assemble(asm_source)
    core.load_program(binary)
    
    # Force CPU into S-mode (1) so that ecall acts as an S-mode ecall (mcause=9)
    state = core.get_state()
    state_data = np.array([
        state['pc'], state['halted'], state['steps_remaining'], 1, state['trap_pending'],
        state['reservation_valid'], state['reservation_addr'], state['uart_tx_len'],
        state['mtime'], state['mtimecmp'],
    ], dtype=np.uint32).tobytes()
    core.queue.write_buffer(core.state_buffer, 0, state_data)

    try:
        # Run until halt (will hit the infinite loop at the end)
        core.run_until_halt(max_cycles=100000)
    except TimeoutError:
        pass # Expected, since it infinite loops at the end

    output = core.read_uart_output()
    print(f"Captured SBI output: {output!r}")
    assert output == b"Hi!", f"Expected b'Hi!', got {output!r}"
    print("✓ SBI Console Putchar successful")

if __name__ == "__main__":
    test_sbi_console_putchar()
