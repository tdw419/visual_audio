/// VCC (Visual Consistency Contract) Integrity Checks
///
/// Computes SHA-256 hashes of table bounding boxes for integrity verification.

use crate::pdb::{BoundingBox, PdbError, PdbResult};
use sha2::{Digest, Sha256};

/// VCC integrity checker
pub struct VccIntegrity {
    /// Cached hashes per table name
    hashes: std::collections::HashMap<String, Vec<u8>>,
}

impl VccIntegrity {
    /// Create new VCC checker
    pub fn new() -> Self {
        Self {
            hashes: std::collections::HashMap::new(),
        }
    }

    /// Compute VCC hash for a table bounding box
    ///
    /// # Arguments
    /// * `canvas` - Full RGBA image
    /// * `table_name` - Name of table
    /// * `bbox` - Bounding box of table
    ///
    /// STUB: Currently returns zero hash
    pub fn compute_table_hash(
        &mut self,
        canvas: &image::RgbaImage,
        table_name: &str,
        bbox: &BoundingBox,
    ) -> PdbResult<Vec<u8>> {
        let mut hasher = Sha256::new();
        for y in bbox.y_min..=bbox.y_max {
            for x in bbox.x_min..=bbox.x_max {
                if x < canvas.width() && y < canvas.height() {
                    let pixel = canvas.get_pixel(x, y);
                    hasher.update(&[pixel[0], pixel[1], pixel[2], pixel[3]]);
                } else {
                    hasher.update(&[0, 0, 0, 0]);
                }
            }
        }
        let hash: Vec<u8> = hasher.finalize().to_vec();
        self.hashes.insert(table_name.to_string(), hash.clone());
        Ok(hash)
    }

    /// Verify table hash matches expected value
    pub fn verify_table(&self, table_name: &str, expected_hash: &[u8]) -> PdbResult<()> {
        let actual_hash = self
            .hashes
            .get(table_name)
            .ok_or(PdbError::VccCheckFailed)?;

        if actual_hash != expected_hash {
            return Err(PdbError::VccCheckFailed);
        }

        Ok(())
    }

    /// Get hash for a table (if computed)
    pub fn get_hash(&self, table_name: &str) -> Option<&[u8]> {
        self.hashes.get(table_name).map(|h| h.as_slice())
    }
}

impl Default for VccIntegrity {
    fn default() -> Self {
        Self::new()
    }
}

/// VCC-specific errors
#[derive(Debug)]
pub enum VccError {
    BoundingBoxOverflow,
    HashComputationFailed,
    HashVerificationFailed,
}

impl From<VccError> for PdbError {
    fn from(err: VccError) -> Self {
        match err {
            VccError::BoundingBoxOverflow => PdbError::VccCheckFailed,
            VccError::HashComputationFailed => PdbError::VccCheckFailed,
            VccError::HashVerificationFailed => PdbError::VccCheckFailed,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vcc_creation() {
        let vcc = VccIntegrity::new();
        assert!(vcc.hashes.is_empty());
    }

    #[test]
    fn test_hash_storage() {
        let mut vcc = VccIntegrity::new();
        let dummy_hash = vec![1u8; 32];
        vcc.hashes.insert("test_table".to_string(), dummy_hash.clone());

        assert_eq!(vcc.get_hash("test_table"), Some(&dummy_hash[..]));
        assert_eq!(vcc.get_hash("nonexistent"), None);
    }

    #[test]
    fn test_verification_success() {
        let mut vcc = VccIntegrity::new();
        let dummy_hash = vec![2u8; 32];
        vcc.hashes.insert("test".to_string(), dummy_hash.clone());

        assert!(vcc.verify_table("test", &dummy_hash).is_ok());
    }

    #[test]
    fn test_verification_failure() {
        let mut vcc = VccIntegrity::new();
        let dummy_hash = vec![3u8; 32];
        vcc.hashes.insert("test".to_string(), dummy_hash.clone());
        let wrong_hash = vec![4u8; 32];

        assert!(matches!(
            vcc.verify_table("test", &wrong_hash),
            Err(PdbError::VccCheckFailed)
        ));
    }

    #[test]
    fn test_table_not_found() {
        let vcc = VccIntegrity::new();
        assert!(matches!(
            vcc.verify_table("nonexistent", &vec![0u8; 32]),
            Err(PdbError::VccCheckFailed)
        ));
    }
}