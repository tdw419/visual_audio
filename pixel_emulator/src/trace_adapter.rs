//! Trace Adapter for PixelRV64VM
//!
//! Bridges RV64 memory accesses to pixel_tracer infrastructure.
//! Records each memory operation as a PixelOperation with source context.

use pixel_tracer::{PixelOpType, PixelOperation, PixelTracer};
use std::path::PathBuf;
use std::time::Instant;

/// Trace adapter configuration
#[derive(Debug, Clone)]
pub struct TraceConfig {
    pub output_dir: PathBuf,
    pub trace_memory_reads: bool,
    pub trace_memory_writes: bool,
    pub trace_instructions: bool,
}

impl Default for TraceConfig {
    fn default() -> Self {
        TraceConfig {
            output_dir: PathBuf::from("./pixel_traces"),
            trace_memory_reads: true,
            trace_memory_writes: true,
            trace_instructions: true,
        }
    }
}

/// Adapter bridging RV64 operations to pixel tracer
pub struct TraceAdapter {
    tracer: PixelTracer,
    config: TraceConfig,
    session_id: Option<String>,
    start_time: Option<Instant>,
    op_count: u64,
}

impl TraceAdapter {
    /// Create new trace adapter with default config
    pub fn new() -> Self {
        Self::with_config(TraceConfig::default())
    }

    /// Create new trace adapter with custom config
    pub fn with_config(config: TraceConfig) -> Self {
        let tracer = PixelTracer::new(config.output_dir.clone());
        TraceAdapter {
            tracer,
            config,
            session_id: None,
            start_time: None,
            op_count: 0,
        }
    }

    /// Start a new trace session
    pub fn start_session(&mut self, command: String) -> String {
        self.session_id = Some(self.tracer.start_trace(command));
        self.start_time = Some(Instant::now());
        self.op_count = 0;
        self.session_id.clone().unwrap()
    }

    /// Stop current trace session
    pub fn stop_session(&mut self) -> Result<PathBuf, String> {
        let session_id = self.session_id.take()
            .ok_or_else(|| "No active session".to_string())?;

        self.tracer.stop_trace(&session_id)
    }

    /// Record a memory read operation
    pub fn record_read(&mut self, addr: u64, size: u32, source: &str) {
        if !self.config.trace_memory_reads {
            return;
        }

        if !self.is_active() {
            return;
        }

        // STUB: Map addr to pixel coordinate
        // TODO: Use Hilbert curve mapping from RV64Memory
        let (x, y) = self.addr_to_pixel(addr);

        let op = PixelOperation {
            op_id: self.op_count,
            timestamp_us: self.elapsed_us(),
            op_type: PixelOpType::Read,
            coord: (x, y),
            size: (size, 1, 1), // Linear read
            data: vec![], // No data capture for reads
            source: source.to_string(),
            pid: 0, // Single-threaded for now
            tid: 0,
        };

        self.tracer.record(op);
        self.op_count += 1;
    }

    /// Record a memory write operation
    pub fn record_write(&mut self, addr: u64, size: u32, data: Vec<u8>, source: &str) {
        if !self.config.trace_memory_writes {
            return;
        }

        if !self.is_active() {
            return;
        }

        // STUB: Map addr to pixel coordinate
        // TODO: Use Hilbert curve mapping from RV64Memory
        let (x, y) = self.addr_to_pixel(addr);

        let op = PixelOperation {
            op_id: self.op_count,
            timestamp_us: self.elapsed_us(),
            op_type: PixelOpType::Write,
            coord: (x, y),
            size: (size, 1, 1), // Linear write
            data, // Capture written data
            source: source.to_string(),
            pid: 0,
            tid: 0,
        };

        self.tracer.record(op);
        self.op_count += 1;
    }

    /// Record an instruction execution
    pub fn record_instruction(&mut self, pc: u64, opcode: &str) {
        if !self.config.trace_instructions {
            return;
        }

        if !self.is_active() {
            return;
        }

        // Record instruction fetch as a read operation
        let (x, y) = self.addr_to_pixel(pc);

        let op = PixelOperation {
            op_id: self.op_count,
            timestamp_us: self.elapsed_us(),
            op_type: PixelOpType::Read,
            coord: (x, y),
            size: (4, 1, 1), // 32-bit instruction
            data: vec![],
            source: format!("INST_{}", opcode),
            pid: 0,
            tid: 0,
        };

        self.tracer.record(op);
        self.op_count += 1;
    }

    /// Get trace statistics from tracer
    pub fn get_stats(&self) -> Option<pixel_tracer::TraceStats> {
        match &self.session_id {
            Some(id) => self.tracer.get_stats(id),
            None => None,
        }
    }

    /// Check if trace is active
    pub fn is_active(&self) -> bool {
        self.session_id.is_some()
    }

    /// Get total operations recorded
    pub fn op_count(&self) -> u64 {
        self.op_count
    }

    // Internal helpers

    fn elapsed_us(&self) -> u64 {
        match &self.start_time {
            Some(start) => start.elapsed().as_micros() as u64,
            None => 0,
        }
    }

    /// Map flat memory address to pixel coordinate (placeholder)
    fn addr_to_pixel(&self, addr: u64) -> (u32, u32) {
        // STUB: Simple 1D mapping for now
        // TODO: Use Hilbert curve matching RV64Memory
        let x = (addr % 4096) as u32;
        let y = (addr / 4096) as u32;
        (x, y)
    }
}

impl Default for TraceAdapter {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_adapter_creation() {
        let adapter = TraceAdapter::new();
        assert!(!adapter.is_active());
        assert_eq!(adapter.op_count(), 0);
    }

    #[test]
    fn test_session_lifecycle() {
        let mut adapter = TraceAdapter::new();

        let session_id = adapter.start_session("test rv64 execution".to_string());
        assert!(!session_id.is_empty());
        assert!(adapter.is_active());

        // Record some operations
        adapter.record_read(0x1000, 4, "test_read");
        adapter.record_write(0x2000, 8, vec![1, 2, 3, 4, 5, 6, 7, 8], "test_write");

        assert_eq!(adapter.op_count(), 2);

        // Stop session
        // Note: We don't actually stop in test to avoid file I/O
    }

    #[test]
    fn test_addr_to_pixel() {
        let adapter = TraceAdapter::new();
        let (x, y) = adapter.addr_to_pixel(0x1000);
        assert_eq!(x, 0x1000);
        assert_eq!(y, 0);

        let (x, y) = adapter.addr_to_pixel(0x5000);
        assert_eq!(x, 0x1000); // Wraps at 4096
        assert_eq!(y, 1);
    }
}