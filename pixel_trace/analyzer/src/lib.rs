//! Pixel Program Analyzer
//!
//! Analyzes trace output to extract pixel operation graphs.
//! Finds patterns, hotspots, and creates "pixel programs" that can be replayed.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::PathBuf;

use pixel_tracer::{PixelOperation, TraceSession, PixelOpType};
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
                if let Some(first_op) = pattern.operations.first() {
                    if op.coord.0 == first_op.relative_coord.0 as u32 {
                        first_occurrence.entry(pattern.pattern_id.clone())
                            .or_insert(op.timestamp_us);
                    }
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
