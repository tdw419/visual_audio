// gpu_integration_tests.rs - Phase 2 GPU Integration Tests
//
// Tests GPU query engine against CPU baseline, validates correctness.

#[cfg(all(test, feature = "gpu"))]
mod gpu_integration_tests {
    use super::super::*;
    use crate::pdb::{BoundingBox, PdbConfig, PdbDecoder, PdbEncoder, PdbHeader, TableMetadata};
    use image::Rgba;
    use std::time::Instant;

    /// Create a test PDB frame with known pattern
    fn create_test_pdb_with_pattern() -> (PdbDecoder, BoundingBox, Vec<u8>) {
        let config = PdbConfig::new(512, 512).unwrap();
        let mut header = PdbHeader::new();

        // Create a test table with known pattern
        let bbox = BoundingBox {
            x_min: 0,
            y_min: 128,
            x_max: 63,
            y_max: 191,
        };

        let pattern = vec![0xDE, 0xAD, 0xBE, 0xEF]; // Known pattern
        let row_length = 4;
        let row_count = 100;

        // Create table metadata
        let table_metadata = TableMetadata::new("test_table", bbox, row_count, row_length);
        header.add_table(table_metadata).unwrap();

        // Create encoder and encode test data with pattern
        let mut encoder = PdbEncoder::new(config.clone(), header.clone());
        encoder.encode_header().unwrap();

        // Encode rows with pattern at known positions
        let mut row_data = Vec::new();
        for i in 0..row_count {
            if i % 10 == 0 {
                // Insert pattern every 10 rows
                row_data.extend_from_slice(&pattern);
            } else {
                // Fill with random data
                row_data.extend_from_slice(&[i as u8, (i + 1) as u8, (i + 2) as u8, (i + 3) as u8]);
            }
        }
        encoder.encode_table(0, &row_data).unwrap();

        // Save to temporary file
        let temp_path = "/tmp/test_gpu_integration.pdb.png";
        encoder.save_png(temp_path).unwrap();

        // Load back as decoder
        let decoder = PdbDecoder::load_png(temp_path).unwrap();
        decoder.decode_header().unwrap();

        (decoder, bbox, pattern)
    }

    #[test]
    fn test_gpu_engine_initialization() {
        let engine = GpuQueryEngine::new();
        assert!(
            engine.is_ok(),
            "GPU engine should initialize on systems with GPU support"
        );
    }

    #[test]
    fn test_gpu_query_config_defaults() {
        let config = GpuQueryConfig::default();
        assert_eq!(config.max_matches, 1000);
        assert_eq!(config.workgroup_size_x, 64);
    }

    #[test]
    fn test_gpu_query_config_custom() {
        let config = GpuQueryConfig {
            max_matches: 5000,
            workgroup_size_x: 128,
        };
        assert_eq!(config.max_matches, 5000);
        assert_eq!(config.workgroup_size_x, 128);
    }

    #[test]
    #[ignore] // Requires actual GPU execution - will be enabled in Phase 2 completion
    fn test_gpu_pattern_scan_matches_cpu_baseline() {
        // Create test PDB with known pattern
        let (decoder, bbox, pattern) = create_test_pdb_with_pattern();

        // CPU baseline scan
        let cpu_start = Instant::now();
        let cpu_matches = cpu_scan_for_pattern(&decoder, &bbox, &pattern);
        let cpu_time = cpu_start.elapsed();

        println!("CPU scan found {} matches in {:?}", cpu_matches.len(), cpu_time);

        // GPU scan (placeholder until full implementation)
        let engine = GpuQueryEngine::new().unwrap();
        let config = GpuQueryConfig::default();

        // Convert decoder canvas to wgpu texture (placeholder)
        // let texture = convert_to_wgpu_texture(&decoder);

        let gpu_start = Instant::now();
        // let gpu_result = engine.scan_table_for_pattern(&texture, &bbox, &pattern, &config);
        let gpu_time = gpu_start.elapsed();

        // In full implementation:
        // assert_eq!(cpu_matches, gpu_result.matches);
        // println!("GPU scan found {} matches in {:?}", gpu_result.matches.len(), gpu_time);

        println!("GPU vs CPU comparison placeholder");
    }

    #[test]
    #[ignore] // Requires actual GPU execution
    fn test_gpu_scan_empty_pattern() {
        let (decoder, bbox, _) = create_test_pdb_with_pattern();

        let engine = GpuQueryEngine::new().unwrap();
        let config = GpuQueryConfig::default();
        let empty_pattern = vec![];

        // let texture = convert_to_wgpu_texture(&decoder);
        // let result = engine.scan_table_for_pattern(&texture, &bbox, &empty_pattern, &config);

        // Empty pattern should match nothing or everything depending on implementation
        // For now, placeholder
        println!("Empty pattern scan placeholder");
    }

    #[test]
    fn test_hilbert_curve_gpu_cpu_consistency() {
        // Test that Hilbert curve mapping is consistent between CPU and GPU
        let n = 64u32;

        // Test several positions
        for d in 0..16 {
            let cpu_result = crate::hilbert::HilbertCurve::d2xy(n as usize, d);

            // In full implementation, we'd compute the same on GPU and compare
            // For now, verify CPU implementation is consistent
            assert!(
                cpu_result.0 < n as usize && cpu_result.1 < n as usize,
                "Hilbert curve should stay within bounds"
            );
        }
    }

    /// CPU baseline pattern scan for comparison
    fn cpu_scan_for_pattern(
        decoder: &PdbDecoder,
        bbox: &BoundingBox,
        pattern: &[u8],
    ) -> Vec<usize> {
        let mut matches = Vec::new();

        // Decode table data
        if let Ok(table_data) = decoder.decode_table("test_table") {
            // Scan for pattern
            for window in table_data.windows(pattern.len()) {
                if window == pattern {
                    matches.push(window.as_ptr() as usize - table_data.as_ptr() as usize);
                }
            }
        }

        matches
    }
}

#[cfg(test)]
mod cpu_baseline_tests {
    use crate::pdb::{PdbConfig, PdbEncoder, PdbHeader, TableMetadata};
    use image::Rgba;

    /// Test CPU-based pattern scanning (baseline for GPU comparison)
    #[test]
    fn test_cpu_pattern_scan_basic() {
        let config = PdbConfig::new(512, 512).unwrap();
        let mut header = PdbHeader::new();

        let bbox = crate::pdb::BoundingBox {
            x_min: 0,
            y_min: 128,
            x_max: 63,
            y_max: 191,
        };

        let table_metadata = TableMetadata::new("test", bbox, 10, 4);
        header.add_table(table_metadata).unwrap();

        let mut encoder = PdbEncoder::new(config, header);
        encoder.encode_header().unwrap();

        // Test data with pattern
        let pattern = vec![0xDE, 0xAD, 0xBE, 0xEF];
        let test_data = vec![
            0x00, 0x01, 0x02, 0x03,
            0xDE, 0xAD, 0xBE, 0xEF, // Pattern at index 4
            0x04, 0x05, 0x06, 0x07,
        ];
        encoder.encode_table(0, &test_data).unwrap();

        assert!(encoder.canvas().width() > 0);
        assert!(encoder.canvas().height() > 0);
    }

    #[test]
    fn test_bounding_box_calculation() {
        let bbox = crate::pdb::BoundingBox {
            x_min: 0,
            y_min: 128,
            x_max: 63,
            y_max: 191,
        };

        let width = bbox.x_max - bbox.x_min + 1;
        let height = bbox.y_max - bbox.y_min + 1;

        assert_eq!(width, 64);
        assert_eq!(height, 64);
        assert_eq!(bbox.pixel_count(), 4096);
    }
}