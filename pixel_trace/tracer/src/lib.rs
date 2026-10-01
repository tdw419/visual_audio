//! Pixel Program Tracer
//!
//! Intercepts and logs all pixel operations during command execution.
//! Maps syscalls and memory accesses to pixel coordinates in VAC2 container.
//!
//! This is how we understand: "When I type 'ls', which pixels change?"

use std::collections::{HashMap, HashSet};
use std::fs::{File, OpenOptions};
use std::io::BufWriter;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PixelOperation {
    /// Sequential operation ID
    pub op_id: u64,
    /// Timestamp in microseconds since trace start
    pub timestamp_us: u64,
    /// Operation type
    pub op_type: PixelOpType,
    /// Virtual coordinate of pixel region
    pub coord: (u32, u32),
    /// Size of region (width, height, depth)
    pub size: (u32, u32, u32),
    /// Data being read/written (truncated if large)
    pub data: Vec<u8>,
    /// System call or memory access that triggered this
    pub source: String,
    /// Process ID
    pub pid: u32,
    /// Thread ID
    pub tid: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PixelOpType {
    Read,
    Write,
    Transform,
    Copy,
    Fill,
    Compress,
    Decompress,
    Unknown(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceSession {
    pub session_id: String,
    pub command: String,
    #[serde(skip, default = "Instant::now")]
    pub start_time: Instant,
    pub operations: Vec<PixelOperation>,
    /// Map of pixel regions accessed by their coordinates
    pub accessed_regions: HashSet<(u32, u32)>,
}

impl TraceSession {
    pub fn new(command: String) -> Self {
        let session_id = format!("trace_{}", chrono::Utc::now().timestamp_micros());
        TraceSession {
            session_id,
            command,
            start_time: Instant::now(),
            operations: Vec::new(),
            accessed_regions: HashSet::new(),
        }
    }

    pub fn record_operation(&mut self, op: PixelOperation) {
        let region_start = op.coord;
        let region_end = (
            op.coord.0 + op.size.0,
            op.coord.1 + op.size.1,
        );

        // Mark all pixels in region as accessed
        for x in region_start.0..region_end.0 {
            for y in region_start.1..region_end.1 {
                self.accessed_regions.insert((x, y));
            }
        }

        self.operations.push(op);
    }

    pub fn duration(&self) -> Duration {
        self.start_time.elapsed()
    }

    pub fn operation_count(&self) -> usize {
        self.operations.len()
    }
}

/// Pixel Tracer - intercepts and logs pixel operations
pub struct PixelTracer {
    sessions: Arc<Mutex<HashMap<String, TraceSession>>>,
    output_dir: PathBuf,
    current_session: Arc<Mutex<Option<String>>>,
}

impl PixelTracer {
    pub fn new(output_dir: PathBuf) -> Self {
        std::fs::create_dir_all(&output_dir).ok();
        PixelTracer {
            sessions: Arc::new(Mutex::new(HashMap::new())),
            output_dir,
            current_session: Arc::new(Mutex::new(None)),
        }
    }

    /// Start tracing a command
    pub fn start_trace(&self, command: String) -> String {
        let session = TraceSession::new(command.clone());
        let session_id = session.session_id.clone();

        {
            let mut sessions = self.sessions.lock().unwrap();
            sessions.insert(session_id.clone(), session);
        }

        {
            let mut current = self.current_session.lock().unwrap();
            *current = Some(session_id.clone());
        }

        println!("Started tracing: {}", command);
        println!("Session ID: {}", session_id);

        session_id
    }

    /// Stop tracing and save results
    pub fn stop_trace(&self, session_id: &str) -> Result<PathBuf, String> {
        {
            let mut current = self.current_session.lock().unwrap();
            *current = None;
        }

        let sessions = self.sessions.lock().unwrap();
        let session = sessions.get(session_id)
            .ok_or_else(|| format!("Session {} not found", session_id))?;

        let output_file = self.output_dir.join(format!("{}.json", session_id));

        // Serialize to JSON
        let json = serde_json::to_string_pretty(&session)
            .map_err(|e| format!("Serialization failed: {}", e))?;

        // Write to file
        std::fs::write(&output_file, json)
            .map_err(|e| format!("Write failed: {}", e))?;

        println!("Trace saved to: {}", output_file.display());
        println!("Operations recorded: {}", session.operation_count());
        println!("Duration: {:?}", session.duration());
        println!("Pixels accessed: {}", session.accessed_regions.len());

        Ok(output_file)
    }

    /// Record a pixel operation
    pub fn record(&self, op: PixelOperation) {
        let current = self.current_session.lock().unwrap();

        if let Some(session_id) = current.as_ref() {
            let mut sessions = self.sessions.lock().unwrap();

            if let Some(session) = sessions.get_mut(session_id) {
                session.record_operation(op);
            }
        }
    }

    /// Get trace statistics
    pub fn get_stats(&self, session_id: &str) -> Option<TraceStats> {
        let sessions = self.sessions.lock().unwrap();
        let session = sessions.get(session_id)?;

        let mut op_counts = HashMap::new();
        let mut byte_counts = HashMap::new();

        for op in &session.operations {
            *op_counts.entry(format!("{:?}", op.op_type)).or_insert(0) += 1;

            let bytes = op.size.0 as u64 * op.size.1 as u64 * op.size.2 as u64;
            *byte_counts.entry(format!("{:?}", op.op_type)).or_insert(0u64) += bytes;
        }

        Some(TraceStats {
            session_id: session_id.to_string(),
            command: session.command.clone(),
            duration: session.duration(),
            total_operations: session.operation_count(),
            accessed_pixels: session.accessed_regions.len(),
            operation_counts: op_counts,
            byte_counts,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceStats {
    pub session_id: String,
    pub command: String,
    pub duration: Duration,
    pub total_operations: usize,
    pub accessed_pixels: usize,
    pub operation_counts: HashMap<String, usize>,
    pub byte_counts: HashMap<String, u64>,
}

impl Default for PixelTracer {
    fn default() -> Self {
        PixelTracer::new(PathBuf::from("./pixel_traces"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trace_session() {
        let session = TraceSession::new("ls /etc".to_string());

        assert_eq!(session.operation_count(), 0);
        assert_eq!(session.accessed_regions.len(), 0);
    }

    #[test]
    fn test_pixel_operation_recording() {
        let mut session = TraceSession::new("test".to_string());

        let op = PixelOperation {
            op_id: 0,
            timestamp_us: 0,
            op_type: PixelOpType::Read,
            coord: (100, 200),
            size: (10, 10, 3),
            data: vec![0; 300],
            source: "ext4_read".to_string(),
            pid: 123,
            tid: 123,
        };

        session.record_operation(op);

        assert_eq!(session.operation_count(), 1);
        assert_eq!(session.accessed_regions.len(), 100); // 10x10 region
    }

    #[test]
    fn test_tracer_lifecycle() {
        let tracer = PixelTracer::new(PathBuf::from("/tmp/test_traces"));

        let session_id = tracer.start_trace("echo test".to_string());
        assert!(!session_id.is_empty());

        // Record an operation
        let op = PixelOperation {
            op_id: 0,
            timestamp_us: 0,
            op_type: PixelOpType::Write,
            coord: (0, 0),
            size: (1, 1, 3),
            data: vec![255; 3],
            source: "stdout_write".to_string(),
            pid: 1,
            tid: 1,
        };

        tracer.record(op);

        // Try to get stats (not stopped yet)
        let stats = tracer.get_stats(&session_id);
        assert!(stats.is_some());

        // Note: We don't stop trace in test to avoid file I/O
    }
}
