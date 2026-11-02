import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from rv64i_checkpoint import load_checkpoint

def print_uart():
    core = load_checkpoint("rv64_inflate_probe/efault_checkpoint.rv64ckpt")
    # Read the entire uart buffer content
    buf = core.queue.read_buffer(core.uart_buffer)
    # The monitor code reads new bytes since _uart_consumed. Let's see how much is in there.
    print("UART consumed offset:", core._uart_consumed)
    # Let's print the entire buffer as bytes/string
    print("UART content:")
    print(bytes(buf).decode('utf-8', 'replace'))

if __name__ == "__main__":
    print_uart()
