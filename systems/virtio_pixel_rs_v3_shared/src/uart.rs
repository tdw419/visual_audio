//! RISC-V UART console output
//!
//! Minimal 16550-compatible UART driver for serial console output
//! Used for debugging in bare-metal environments

pub struct UART;

pub const UART_BASE: usize = 0x10000000;

impl UART {
    pub const unsafe fn init() -> Self {
        UART
    }

    pub fn putc(&self, c: u8) {
        unsafe {
            // Wait for transmit holding register to be empty (bit 5 of LSR)
            let lsr = (UART_BASE + 5) as *mut u8;
            let thr = (UART_BASE + 0) as *mut u8;
            while lsr.read_volatile() & 0x20 == 0 {}
            thr.write_volatile(c);
        }
    }

    pub fn puts(&self, s: &str) {
        for b in s.bytes() {
            if b == b'\n' {
                self.putc(b'\r');
            }
            self.putc(b);
        }
    }
}

impl core::fmt::Write for UART {
    fn write_str(&mut self, s: &str) -> core::fmt::Result {
        self.puts(s);
        Ok(())
    }
}