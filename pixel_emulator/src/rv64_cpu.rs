//! RV64 CPU State
//!
//! Implements RISC-V RV64I register file and CSR registers.
//! Follows RISC-V Privileged Architecture spec v1.12.

use serde::{Deserialize, Serialize};

/// Privilege modes
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PrivilegeMode {
    User = 0,
    Supervisor = 1,
    Reserved = 2,
    Machine = 3,
}

impl PrivilegeMode {
    pub fn from_u8(val: u8) -> Self {
        match val {
            0 => PrivilegeMode::User,
            1 => PrivilegeMode::Supervisor,
            3 => PrivilegeMode::Machine,
            _ => PrivilegeMode::Reserved,
        }
    }
}

/// General-purpose registers (32 × 64-bit)
pub type GPR = [u64; 32];

/// CSR (Control and Status Registers) subset
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CSR {
    /// mstatus - Machine status register
    pub mstatus: u64,
    /// mtvec - Machine trap handler base address
    pub mtvec: u64,
    /// mepc - Machine exception program counter
    pub mepc: u64,
    /// mcause - Machine trap cause
    pub mcause: u64,
    /// mtval - Machine trap value
    pub mtval: u64,
    /// mie - Machine interrupt enable
    pub mie: u64,
    /// mip - Machine interrupt pending
    pub mip: u64,
}

impl Default for CSR {
    fn default() -> Self {
        CSR {
            mstatus: 0,
            mtvec: 0,
            mepc: 0,
            mcause: 0,
            mtval: 0,
            mie: 0,
            mip: 0,
        }
    }
}

/// RV64 CPU state
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RV64CPU {
    /// General-purpose registers
    pub x: GPR,
    /// Program counter
    pub pc: u64,
    /// CSR registers
    pub csr: CSR,
    /// Current privilege mode
    pub privilege: PrivilegeMode,
}

impl Default for RV64CPU {
    fn default() -> Self {
        RV64CPU {
            x: [0u64; 32],
            pc: 0,
            csr: CSR::default(),
            privilege: PrivilegeMode::Machine,
        }
    }
}

impl RV64CPU {
    pub fn new() -> Self {
        Self::default()
    }

    /// Read GPR register
    pub fn read_gpr(&self, reg: u8) -> u64 {
        assert!(reg < 32, "Invalid register: {}", reg);
        // x0 is hardwired to zero
        if reg == 0 {
            0
        } else {
            self.x[reg as usize]
        }
    }

    /// Write GPR register
    pub fn write_gpr(&mut self, reg: u8, val: u64) {
        assert!(reg < 32, "Invalid register: {}", reg);
        // x0 is hardwired to zero
        if reg != 0 {
            self.x[reg as usize] = val;
        }
    }

    /// Read CSR register
    pub fn read_csr(&self, csr_addr: u16) -> Option<u64> {
        // STUB: Implement CSR read decoding
        // TODO: Map csr_addr to CSR struct fields
        match csr_addr {
            0x300 => Some(self.csr.mstatus),
            0x305 => Some(self.csr.mtvec),
            0x341 => Some(self.csr.mepc),
            0x342 => Some(self.csr.mcause),
            0x343 => Some(self.csr.mtval),
            0x304 => Some(self.csr.mie),
            0x344 => Some(self.csr.mip),
            _ => {
                log::warn!("Unimplemented CSR read: 0x{:03x}", csr_addr);
                None
            }
        }
    }

    /// Write CSR register
    pub fn write_csr(&mut self, csr_addr: u16, val: u64) -> Result<(), String> {
        // STUB: Implement CSR write decoding
        // TODO: Map csr_addr to CSR struct fields
        // TODO: Handle read-only CSRs (trap if written)
        match csr_addr {
            0x300 => {
                self.csr.mstatus = val;
                Ok(())
            }
            0x305 => {
                self.csr.mtvec = val;
                Ok(())
            }
            0x341 => {
                self.csr.mepc = val;
                Ok(())
            }
            0x342 => {
                self.csr.mcause = val;
                Ok(())
            }
            0x343 => {
                self.csr.mtval = val;
                Ok(())
            }
            0x304 => {
                self.csr.mie = val;
                Ok(())
            }
            0x344 => {
                self.csr.mip = val;
                Ok(())
            }
            _ => {
                log::warn!("Unimplemented CSR write: 0x{:03x}", csr_addr);
                Err(format!("Unknown CSR: 0x{:03x}", csr_addr))
            }
        }
    }

    /// Raise exception/trap
    pub fn raise_exception(&mut self, cause: u64, val: u64) {
        // STUB: Implement trap handling
        // TODO: Save PC to mepc
        // TODO: Set mcause, mtval
        // TODO: Jump to mtvec
        self.csr.mepc = self.pc;
        self.csr.mcause = cause;
        self.csr.mtval = val;
        self.pc = self.csr.mtvec;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gpr_read_write() {
        let mut cpu = RV64CPU::new();
        cpu.write_gpr(1, 0xDEADBEEF);
        assert_eq!(cpu.read_gpr(1), 0xDEADBEEF);
    }

    #[test]
    fn test_x0_hardwired_zero() {
        let mut cpu = RV64CPU::new();
        cpu.write_gpr(0, 0xFFFFFFFF);
        assert_eq!(cpu.read_gpr(0), 0);
    }

    #[test]
    fn test_csr_mstatus_rw() {
        let mut cpu = RV64CPU::new();
        cpu.write_csr(0x300, 0x1234).unwrap();
        assert_eq!(cpu.read_csr(0x300), Some(0x1234));
    }

    #[test]
    fn test_exception_state() {
        let mut cpu = RV64CPU::new();
        cpu.pc = 0x1000;
        cpu.raise_exception(2, 0x1004); // Instruction access fault

        assert_eq!(cpu.csr.mepc, 0x1000);
        assert_eq!(cpu.csr.mcause, 2);
        assert_eq!(cpu.csr.mtval, 0x1004);
    }
}