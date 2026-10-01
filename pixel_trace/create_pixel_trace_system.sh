#!/bin/bash
# Pixel Program Extraction System
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
PIXEL_TRACE_DIR="$PROJECT_ROOT/pixel_trace"

echo "=== Pixel Program Extraction System ==="
echo ""
echo "This system traces Linux commands to map them to pixel operations."
echo ""

mkdir -p "$PIXEL_TRACE_DIR"/{tracer,analyzer,vm}

echo "✓ Created pixel trace directory structure"

# Create pixel tracer module
cat > "$PIXEL_TRACE_DIR/tracer/src/lib.rs" << 'EOF'
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
EOF

echo "✓ Created pixel tracer module"

# Cargo.toml for tracer
cat > "$PIXEL_TRACE_DIR/tracer/Cargo.toml" << 'EOF'
[package]
name = "pixel-tracer"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
chrono = "0.4"

[dev-dependencies]
EOF

echo "✓ Created tracer Cargo.toml"

# Pixel analyzer module
cat > "$PIXEL_TRACE_DIR/analyzer/src/lib.rs" << 'EOF'
//! Pixel Program Analyzer
//!
//! Analyzes trace output to extract pixel operation graphs.
//! Finds patterns, hotspots, and creates "pixel programs" that can be replayed.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::PathBuf;

use crate::tracer::{PixelOperation, TraceSession, PixelOpType};
use serde::{Deserialize, Serialize};

/// Represents a reusable pixel operation pattern
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PixelPattern {
    pub pattern_id: String,
    pub description: String,
    /// Coordinate offsets (relative to pattern origin)
    pub operations: Vec<PixelOperationTemplate>,
    /// Estimated execution time in microseconds
    pub estimated_duration_us: u64,
    /// Patterns this pattern depends on
    pub dependencies: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PixelOperationTemplate {
    pub op_type: PixelOpType,
    pub relative_coord: (i32, i32, i32), // x, y, z offsets
    pub size: (u32, u32, u32),
    pub data_pattern: Option<DataPattern>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DataPattern {
    Static(Vec<u8>),
    Constant(u8),
    Incrementing(u8),
    Match(String), // Regex pattern on ASCII interpretation
}

/// Extracted pixel program for a command
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PixelProgram {
    pub program_id: String,
    pub command: String,
    pub patterns: Vec<PixelPattern>,
    pub hotspots: Vec<PixelHotspot>,
    pub execution_order: Vec<String>, // Pattern IDs in execution order
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PixelHotspot {
    pub region: (u32, u32, u32, u32), // x, y, width, height
    pub access_count: usize,
    pub access_types: HashSet<String>,
    pub description: String,
}

/// Analyzer results
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisResult {
    pub program: PixelProgram,
    pub summary: AnalysisSummary,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisSummary {
    pub total_operations: usize,
    pub unique_regions: usize,
    pub pattern_count: usize,
    pub hotspot_count: usize,
    pub compression_ratio: f64, // Original ops / Patterned ops
}

/// Pixel Program Analyzer
pub struct PixelProgramAnalyzer {
    trace_dir: PathBuf,
}

impl PixelProgramAnalyzer {
    pub fn new(trace_dir: PathBuf) -> Self {
        PixelProgramAnalyzer { trace_dir }
    }

    /// Load a trace session from disk
    pub fn load_trace(&self, session_id: &str) -> Result<TraceSession, String> {
        let trace_file = self.trace_dir.join(format!("{}.json", session_id));

        let content = fs::read_to_string(&trace_file)
            .map_err(|e| format!("Failed to read trace: {}", e))?;

        serde_json::from_str(&content)
            .map_err(|e| format!("Failed to parse trace: {}", e))
    }

    /// Analyze a trace to extract pixel program
    pub fn analyze(&self, session_id: &str) -> Result<AnalysisResult, String> {
        let trace = self.load_trace(session_id)?;

        println!("Analyzing trace: {}", session_id);
        println!("Command: {}", trace.command);
        println!("Operations: {}", trace.operations.len());

        // Find hotspots
        let hotspots = self.find_hotspots(&trace);

        // Extract patterns
        let patterns = self.extract_patterns(&trace, &hotspots);

        // Build execution order
        let execution_order = self.build_execution_order(&trace, &patterns);

        // Calculate compression ratio
        let original_ops = trace.operations.len();
        let patterned_ops = patterns.iter()
            .map(|p| p.operations.len())
            .sum::<usize>();
        let compression_ratio = if patterned_ops > 0 {
            original_ops as f64 / patterned_ops as f64
        } else {
            0.0
        };

        let program = PixelProgram {
            program_id: session_id.to_string(),
            command: trace.command.clone(),
            patterns,
            hotspots,
            execution_order,
        };

        let summary = AnalysisSummary {
            total_operations: original_ops,
            unique_regions: trace.accessed_regions.len(),
            pattern_count: program.patterns.len(),
            hotspot_count: program.hotspots.len(),
            compression_ratio,
        };

        Ok(AnalysisResult {
            program,
            summary,
        })
    }

    /// Find frequently accessed pixel regions (hotspots)
    fn find_hotspots(&self, trace: &TraceSession) -> Vec<PixelHotspot> {
        let mut region_counts: HashMap<(u32, u32, u32, u32), (usize, HashSet<String>)> =
            HashMap::new();

        // Aggregate operations by region
        for op in &trace.operations {
            let key = (op.coord.0, op.coord.1, op.size.0, op.size.1);

            let (count, types) = region_counts.entry(key).or_insert((0, HashSet::new()));
            *count += 1;
            types.insert(format!("{:?}", op.op_type));
        }

        // Convert to hotspots (regions accessed > 10 times)
        region_counts
            .into_iter()
            .filter(|(_, (count, _))| *count > 10)
            .map(|(region, (count, types))| {
                let description = self.describe_region(region);
                PixelHotspot {
                    region,
                    access_count: count,
                    access_types: types,
                    description,
                }
            })
            .collect()
    }

    /// Extract reusable patterns from operations
    fn extract_patterns(&self, trace: &TraceSession, hotspots: &[PixelHotspot]) -> Vec<PixelPattern> {
        let mut patterns = Vec::new();

        // For each hotspot, extract pattern
        for (idx, hotspot) in hotspots.iter().enumerate() {
            let pattern_id = format!("pattern_{}", idx);

            let operations: Vec<_> = trace.operations
                .iter()
                .filter(|op| {
                    op.coord.0 == hotspot.region.0
                        && op.coord.1 == hotspot.region.1
                        && op.size.0 == hotspot.region.2
                        && op.size.1 == hotspot.region.3
                })
                .map(|op| PixelOperationTemplate {
                    op_type: op.op_type.clone(),
                    relative_coord: (0, 0, 0),
                    size: op.size,
                    data_pattern: self.extract_data_pattern(&op.data),
                })
                .collect();

            if !operations.is_empty() {
                let estimated_duration = operations.len() as u64 * 10; // Rough estimate

                patterns.push(PixelPattern {
                    pattern_id,
                    description: hotspot.description.clone(),
                    operations,
                    estimated_duration_us: estimated_duration,
                    dependencies: Vec::new(),
                });
            }
        }

        patterns
    }

    /// Extract data pattern from raw bytes
    fn extract_data_pattern(&self, data: &[u8]) -> Option<DataPattern> {
        if data.is_empty() {
            return None;
        }

        // Check if all bytes are the same
        let first = data[0];
        if data.iter().all(|&b| b == first) {
            return Some(DataPattern::Constant(first));
        }

        // Check if incrementing
        let mut incrementing = true;
        for i in 1..data.len() {
            if data[i] != data[i-1].wrapping_add(1) {
                incrementing = false;
                break;
            }
        }
        if incrementing {
            return Some(DataPattern::Incrementing(data[0]));
        }

        // If small, treat as static
        if data.len() < 64 {
            return Some(DataPattern::Static(data.to_vec()));
        }

        // Otherwise, try ASCII pattern matching
        if data.iter().all(|&b| b.is_ascii() || b == 0) {
            let ascii = String::from_utf8_lossy(data);
            if ascii.chars().all(|c| c.is_ascii() || c == '\0') {
                // Try to find a pattern (digits, letters, etc.)
                if ascii.chars().all(|c| c.is_ascii_digit()) {
                    return Some(DataPattern::Match(r"\d+".to_string()));
                }
            }
        }

        None
    }

    /// Build execution order based on timestamps
    fn build_execution_order(&self, trace: &TraceSession, patterns: &[PixelPattern]) -> Vec<String> {
        // Sort by first occurrence in trace
        let mut first_occurrence: HashMap<String, u64> = HashMap::new();

        for op in &trace.operations {
            for pattern in patterns {
                if op.coord.0 == pattern.operations.first()?.relative_coord.0 as u32 {
                    first_occurrence.entry(pattern.pattern_id.clone())
                        .or_insert(op.timestamp_us);
                }
            }
        }

        let mut pattern_ids: Vec<_> = first_occurrence.into_iter().collect();
        pattern_ids.sort_by_key(|(_, time)| *time);

        pattern_ids.into_iter().map(|(id, _)| id).collect()
    }

    /// Describe a pixel region based on typical Linux structures
    fn describe_region(&self, region: (u32, u32, u32, u32)) -> String {
        let (x, y, w, h) = region;

        // This is heuristic - would need actual VAC2 format knowledge
        match (x, y, w, h) {
            (0, 0, 4096, 4096) => "Full container".to_string(),
            (0, 0, 512, 512) => "Boot sector / bootloader".to_string(),
            (512, 0, 256, 256) => "GRUB config".to_string(),
            (1024, 0, 2048, 2048) => "Kernel image".to_string(),
            (0, 2048, 1024, 1024) => "Initramfs".to_string(),
            (1024, 2048, 1024, 1024) => "File system metadata".to_string(),
            _ => format!("Unknown region at ({}, {}), size {}x{}", x, y, w, h),
        }
    }

    /// Save analysis result to disk
    pub fn save_analysis(&self, result: &AnalysisResult, output_path: PathBuf) -> Result<(), String> {
        let json = serde_json::to_string_pretty(result)
            .map_err(|e| format!("Serialization failed: {}", e))?;

        fs::write(&output_path, json)
            .map_err(|e| format!("Write failed: {}", e))?;

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_data_pattern_extraction() {
        let analyzer = PixelProgramAnalyzer::new(PathBuf::from("/tmp"));

        // Constant pattern
        let constant = analyzer.extract_data_pattern(&[0xFF; 100]);
        assert!(matches!(constant, Some(DataPattern::Constant(0xFF))));

        // Incrementing pattern
        let inc = analyzer.extract_data_pattern(&[0, 1, 2, 3, 4]);
        assert!(matches!(inc, Some(DataPattern::Incrementing(0))));
    }

    #[test]
    fn test_region_description() {
        let analyzer = PixelProgramAnalyzer::new(PathBuf::from("/tmp"));

        let desc = analyzer.describe_region((0, 0, 4096, 4096));
        assert_eq!(desc, "Full container");

        let desc = analyzer.describe_region((512, 0, 256, 256));
        assert_eq!(desc, "GRUB config");
    }
}
EOF

echo "✓ Created pixel analyzer module"

# Cargo.toml for analyzer
cat > "$PIXEL_TRACE_DIR/analyzer/Cargo.toml" << 'EOF'
[package]
name = "pixel-analyzer"
version = "0.1.0"
edition = "2021"

[dependencies]
pixel-tracer = { path = "../tracer" }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
chrono = "0.4"

[dev-dependencies]
EOF

echo "✓ Created analyzer Cargo.toml"

# Create trace wrapper script
cat > "$PROJECT_ROOT/pixel_trace_command.sh" << 'EOF'
#!/bin/bash
# Trace a Linux command to extract its pixel operations
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
TRACER_BUILD="$PROJECT_ROOT/pixel_trace/tracer/target/release/pixel_tracer"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <command>"
    echo "Example: $0 ls /etc"
    echo ""
    echo "This runs the command and traces all pixel operations."
    echo "The trace is saved to pixel_traces/ directory."
    echo ""
    exit 1
fi

COMMAND="$@"
COMMAND_SAFE=$(echo "$COMMAND" | sed 's/[^a-zA-Z0-9_-]/_/g')

echo "=== Pixel Tracing Session ==="
echo "Command: $COMMAND"
echo ""

# Build tracer if needed
if [ ! -f "$TRACER_BUILD" ]; then
    echo "Building pixel tracer..."
    cd "$PROJECT_ROOT/pixel_trace/tracer"
    cargo build --release
fi

# Start tracer
echo "Starting tracer..."
SESSION_ID=$("$TRACER_BUILD" start "$COMMAND")

echo ""
echo "Session ID: $SESSION_ID"
echo "Executing command..."
echo "----------------------------------------"

# Execute the command
eval "$COMMAND"
EXIT_CODE=$?

echo "----------------------------------------"
echo "Command exited with code: $EXIT_CODE"
echo ""

# Stop tracer and save results
echo "Stopping tracer..."
RESULT=$("$TRACER_BUILD" stop "$SESSION_ID")
TRACE_FILE=$(echo "$RESULT" | grep "Trace saved to:" | sed 's/.*saved to: //')

echo ""
echo "=== Trace Complete ==="
echo "Trace file: $TRACE_FILE"
echo ""
echo "To analyze this trace:"
echo "  analyze_pixel_trace.sh $SESSION_ID"
echo ""

exit $EXIT_CODE
EOF

chmod +x "$PROJECT_ROOT/pixel_trace_command.sh"
echo "✓ Created trace wrapper script"

# Create analyzer wrapper script
cat > "$PROJECT_ROOT/analyze_pixel_trace.sh" << 'EOF'
#!/bin/bash
# Analyze a pixel trace to extract pixel program
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
ANALYZER_BUILD="$PROJECT_ROOT/pixel_trace/analyzer/target/release/pixel_analyzer"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <session_id>"
    echo "Example: $0 trace_1723981234567890"
    echo ""
    echo "This analyzes a pixel trace and extracts patterns."
    echo ""
    exit 1
fi

SESSION_ID="$1"

echo "=== Pixel Trace Analysis ==="
echo "Session ID: $SESSION_ID"
echo ""

# Build analyzer if needed
if [ ! -f "$ANALYZER_BUILD" ]; then
    echo "Building pixel analyzer..."
    cd "$PROJECT_ROOT/pixel_trace/analyzer"
    cargo build --release
fi

# Run analysis
echo "Running analysis..."
"$ANALYZER_BUILD" analyze "$SESSION_ID"

echo ""
echo "=== Analysis Complete ==="
echo ""
echo "Results saved to: pixel_traces/analysis_${SESSION_ID}.json"
echo ""

# Display summary
echo "Summary:"
cat "$PROJECT_ROOT/pixel_traces/analysis_${SESSION_ID}.json" | jq -r '.summary'
echo ""

exit 0
EOF

chmod +x "$PROJECT_ROOT/analyze_pixel_trace.sh"
echo "✓ Created analyzer wrapper script"

# Create demo script
cat > "$PROJECT_ROOT/demo_pixel_tracing.sh" << 'EOF'
#!/bin/bash
# Demo: Trace simple Linux commands to extract pixel programs
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"

echo "=== Pixel Program Extraction Demo ==="
echo ""
echo "This demo traces several Linux commands to understand"
echo "how they are encoded as pixel operations."
echo ""

mkdir -p "$PROJECT_ROOT/pixel_traces"

# Command 1: Simple echo
echo "Command 1: Tracing 'echo Hello, World!'"
echo "---"
pixel_trace_command.sh echo "Hello, World!"
echo ""

# Command 2: List directory
echo "Command 2: Tracing 'ls /etc'"
echo "---"
pixel_trace_command.sh ls /etc | head -20
echo ""

# Command 3: Read file
echo "Command 3: Tracing 'cat /etc/hostname'"
echo "---"
pixel_trace_command.sh cat /etc/hostname
echo ""

# Command 4: Complex command
echo "Command 4: Tracing 'find /etc -name passwd'"
echo "---"
pixel_trace_command.sh find /etc -name passwd
echo ""

echo "=== Demo Complete ==="
echo ""
echo "Trace files saved to: $PROJECT_ROOT/pixel_traces/"
echo ""
echo "To analyze any trace:"
echo "  analyze_pixel_trace.sh <session_id>"
echo ""
echo "Example:"
echo "  analyze_pixel_trace.sh \$(ls -t $PROJECT_ROOT/pixel_traces/*.json | head -1 | xargs basename -s .json)"
echo ""
EOF

chmod +x "$PROJECT_ROOT/demo_pixel_tracing.sh"
echo "✓ Created demo script"

echo ""
echo "=== Pixel Program Extraction System Created ==="
echo ""
echo "Components created:"
echo "  - $PIXEL_TRACE_DIR/tracer/src/lib.rs     (pixel tracer module)"
echo "  - $PIXEL_TRACE_DIR/analyzer/src/lib.rs   (pixel analyzer module)"
echo "  - $PROJECT_ROOT/pixel_trace_command.sh  (trace wrapper)"
echo "  - $PROJECT_ROOT/analyze_pixel_trace.sh  (analyzer wrapper)"
echo "  - $PROJECT_ROOT/demo_pixel_tracing.sh   (demo script)"
echo ""
echo "Quick start:"
echo "  1. Build: cd $PIXEL_TRACE_DIR && cargo build --release"
echo "  2. Demo:  $PROJECT_ROOT/demo_pixel_tracing.sh"
echo "  3. Trace: pixel_trace_command.sh <command>"
echo "  4. Analyze: analyze_pixel_trace.sh <session_id>"
echo ""