//! Pixel-Based RISC-V RV64 Emulator
//!
//! Adapts the Pixel VM infrastructure for RISC-V RV64I emulation.
//! Core concept: Use PixelContainer as backing storage, map flat memory
//! addresses to pixel coordinates via Hilbert curve.
//!
//! Architecture:
//! ┌─────────────────────────────────────────────────────────────────┐
//! │                     PixelRV64VM                                 │
//! │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────────┐ │
//! │  │   RV64CPU   │  │  RV64Memory │  │      TraceAdapter         │ │
//! │  │  (GPRs/CSR) │  │ (PixelAddr) │  │  (PixelTracer bridge)    │ │
//! │  └──────┬──────┘  └──────┬──────┘  └───────────┬──────────────┘ │
//! │         │                │                    │                 │
//! │         └────────────────┼────────────────────┘                 │
//! │                          ↓                                      │
//! │                  PixelContainer (backing store)                │
//! └─────────────────────────────────────────────────────────────────┘

pub mod hilbert;
pub mod rv64_cpu;
pub mod rv64_decode;
pub mod rv64_memory;
pub mod trace_adapter;

pub use rv64_cpu::{RV64CPU, PrivilegeMode, CSR};
pub use rv64_decode::{RV64Opcode, RV64Instruction, DecodeError};
pub use rv64_memory::{RV64Memory, MemoryError};
pub use trace_adapter::TraceAdapter;

/// RV64 emulator configuration
#[derive(Debug, Clone)]
pub struct RV64Config {
    /// Memory size in bytes (must be page-aligned)
    pub memory_size: u64,
    /// Enable tracing to pixel_tracer
    pub enable_tracing: bool,
    /// Trace output directory
    pub trace_dir: Option<String>,
    /// Page size for Sv39 MMU (default 4096)
    pub page_size: u64,
}

impl Default for RV64Config {
    fn default() -> Self {
        RV64Config {
            memory_size: 64 * 1024 * 1024, // 64MB
            enable_tracing: false,
            trace_dir: None,
            page_size: 4096,
        }
    }
}

/// RV64 execution statistics
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct RV64Stats {
    pub instructions_executed: usize,
    pub memory_reads: usize,
    pub memory_writes: usize,
    pub branch_taken: usize,
    pub branch_not_taken: usize,
    pub cycles: u64,
    pub privileged_ops: usize,
}

/// RV64 emulator main entry point
pub struct RV64VM {
    cpu: RV64CPU,
    memory: RV64Memory,
    tracer: Option<TraceAdapter>,
    stats: RV64Stats,
    halted: bool,
}

impl RV64VM {
    /// Create new RV64 VM with default config
    pub fn new() -> Self {
        Self::with_config(RV64Config::default())
    }

    /// Create new RV64 VM with custom config
    pub fn with_config(config: RV64Config) -> Self {
        // STUB: Initialize all components
        // TODO: Create PixelContainer with appropriate dimensions
        // TODO: Initialize RV64Memory with PixelContainer backing
        // TODO: Set up TraceAdapter if config.enable_tracing
        todo!("Initialize VM with config: {:?}", config)
    }

    /// Load binary into memory at specified address
    pub fn load_binary(&mut self, addr: u64, data: &[u8]) -> Result<(), MemoryError> {
        // STUB: Copy data into PixelContainer at flat address
        // TODO: Map flat addr → pixel coordinate via Hilbert
        // TODO: Write bytes through PixelContainer::write_region
        let _addr = addr;
        let _data = data;
        todo!("Load binary at addr 0x{:x}, len {}", addr, data.len())
    }

    /// Execute one instruction
    pub fn step(&mut self) -> Result<(), String> {
        // STUB: Fetch → Decode → Execute cycle
        // TODO: Fetch instruction word from current PC
        // TODO: Decode using RV64Decoder
        // TODO: Execute on RV64CPU
        // TODO: Update stats
        todo!("Execute single instruction")
    }

    /// Run until halted (e.g., ECALL exit)
    pub fn run(&mut self) -> Result<RV64Stats, String> {
        // STUB: Execute until halt condition
        while !self.halted {
            self.step()?;
        }
        Ok(self.stats.clone())
    }

    /// Halt execution
    pub fn halt(&mut self) {
        self.halted = true;
    }

    /// Get current execution statistics
    pub fn stats(&self) -> &RV64Stats {
        &self.stats
    }

    /// Get CPU state snapshot
    pub fn cpu_state(&self) -> &RV64CPU {
        &self.cpu
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vm_creation() {
        let vm = RV64VM::new();
        // Verify initialized state
        assert!(!vm.halted);
    }

    #[test]
    fn test_config_defaults() {
        let config = RV64Config::default();
        assert_eq!(config.memory_size, 64 * 1024 * 1024);
        assert_eq!(config.page_size, 4096);
        assert!(!config.enable_tracing);
    }
}