#![cfg_attr(not(feature = "std"), no_std)]

pub mod hilbert;
#[cfg(feature = "std")]
pub mod canvas;
#[cfg(feature = "std")]
pub mod pdb;

pub use hilbert::HilbertCurve;
#[cfg(feature = "std")]
pub use canvas::PixelCanvas;
#[cfg(feature = "std")]
pub use pdb::{PdbEncoder, PdbDecoder, VccIntegrity, SqliteToPdb};
#[cfg(all(feature = "std", feature = "gpu"))]
pub use pdb::GpuQueryEngine;
