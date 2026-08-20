//! Predictive frame cache manager for MKV frames
//!
//! This module implements a cache manager that:
//! 1. Pre-fetches and caches sequential frames ahead of guest OS reads
//! 2. Maintains an LRU cache of decoded frames in GPU memory
//! 3. Predicts future reads based on sequential access patterns
//!
//! # Architecture
//!
//! ```text
//! Guest read request → Check cache
//!     ├─ Hit: Return texture instantly (0-1ms)
//!     └─ Miss: Decode + cache + prefetch next N frames (2-10ms)
//! ```

use anyhow::{Context, Result};
use crossbeam_channel::{bounded, Receiver, Sender};
use log::{info, warn};
use lru::LruCache;
use std::collections::VecDeque;
use std::num::NonZeroUsize;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::thread;
use wgpu::{Device, Queue};

use super::hw_decoder::HardwareDecoder;
use super::wgpu_texture_loader;

/// Cache manager configuration
#[derive(Debug, Clone)]
pub struct CacheConfig {
    /// Number of frames to pre-fetch ahead
    pub prefetch_depth: usize,

    /// Maximum cache size (in frames)
    pub max_cache_size: usize,
}

impl Default for CacheConfig {
    fn default() -> Self {
        Self {
            prefetch_depth: 20,
            max_cache_size: 50,
        }
    }
}

/// Message sent to the background prefetch thread
#[derive(Debug)]
enum PrefetchMessage {
    /// Request to pre-fetch frames starting from this index
    Prefetch { start_frame: usize, count: usize },

    /// Stop the prefetch thread
    Stop,
}

/// Predictive frame cache manager
pub struct CacheManager {
    /// LRU cache: frame index → WGPU texture (wrapped in Arc for shared ownership)
    cache: Arc<Mutex<LruCache<usize, Arc<wgpu::Texture>>>>,

    /// WGPU device (for texture creation)
    pub wgpu_device: Arc<Device>,

    /// WGPU queue (for texture upload)
    pub wgpu_queue: Arc<Queue>,

    /// Background prefetch thread handle
    prefetch_thread: Option<thread::JoinHandle<()>>,

    /// Channel for sending prefetch requests
    prefetch_tx: Option<Sender<PrefetchMessage>>,

    /// Recent read patterns (for prediction)
    read_pattern: VecDeque<usize>,

    /// Configuration
    config: CacheConfig,

    /// MKV file path
    mkv_path: PathBuf,
}

impl CacheManager {
    /// Create a new cache manager
    ///
    /// This will:
    /// 1. Initialize the hardware decoder
    /// 2. Start the background prefetch thread
    /// 3. Initialize the LRU cache
    pub fn new<P: AsRef<std::path::Path>>(mkv_path: P, config: CacheConfig) -> Result<Self> {
        let mkv_path = mkv_path.as_ref().to_path_buf();

        info!(
            "Initializing cache manager: prefetch_depth={}, max_cache_size={}",
            config.prefetch_depth, config.max_cache_size
        );

        // Initialize LRU cache (wrapped in Arc<Mutex<>> for thread-safe shared access)
        let cache = Arc::new(Mutex::new(LruCache::new(
            NonZeroUsize::new(config.max_cache_size).unwrap(),
        )));

        // Initialize WGPU device using existing function
        let (_instance, _adapter, wgpu_device, wgpu_queue) = wgpu_texture_loader::init_wgpu()?;
        let wgpu_device = Arc::new(wgpu_device);
        let wgpu_queue = Arc::new(wgpu_queue);

        // Create channels for prefetch communication
        let (prefetch_tx, prefetch_rx) = bounded(config.prefetch_depth);

        // Start background prefetch thread with shared cache reference
        let prefetch_thread = Self::start_prefetch_thread(
            mkv_path.clone(),
            prefetch_rx,
            wgpu_device.clone(),
            wgpu_queue.clone(),
            cache.clone(),
        )?;

        info!("Cache manager ready");

        Ok(Self {
            cache,
            wgpu_device,
            wgpu_queue,
            prefetch_thread: Some(prefetch_thread),
            prefetch_tx: Some(prefetch_tx),
            read_pattern: VecDeque::with_capacity(10),
            config,
            mkv_path,
        })
    }

    /// Start the background prefetch thread
    fn start_prefetch_thread(
        mkv_path: PathBuf,
        prefetch_rx: Receiver<PrefetchMessage>,
        wgpu_device: Arc<Device>,
        wgpu_queue: Arc<Queue>,
        cache: Arc<Mutex<LruCache<usize, Arc<wgpu::Texture>>>>,
    ) -> Result<thread::JoinHandle<()>> {
        info!("Starting background prefetch thread");

        let handle = thread::spawn(move || {
            // Initialize hardware decoder in this thread
            let mut decoder = match HardwareDecoder::new(&mkv_path) {
                Ok(d) => d,
                Err(e) => {
                    warn!("Failed to initialize decoder in prefetch thread: {}", e);
                    return;
                }
            };

            info!("Prefetch thread initialized");

            // Process prefetch requests
            for msg in prefetch_rx.iter() {
                match msg {
                    PrefetchMessage::Prefetch { start_frame, count } => {
                        info!("Prefetching {} frames starting at {}", count, start_frame);

                        for i in 0..count {
                            let frame_idx = start_frame + i;

                            // Check if frame is already cached
                            {
                                let cache_guard = cache.lock().unwrap();
                                if cache_guard.contains(&frame_idx) {
                                    info!("Frame {} already cached, skipping", frame_idx);
                                    continue;
                                }
                            }

                            // Decode frame
                            match decoder.decode_frame_to_texture(&wgpu_device, &wgpu_queue, frame_idx) {
                                Ok(texture) => {
                                    let texture_arc = Arc::new(texture);
                                    let mut cache_guard = cache.lock().unwrap();
                                    cache_guard.put(frame_idx, texture_arc);
                                    info!("Prefetched frame {} (cached)", frame_idx);
                                }
                                Err(e) => {
                                    warn!("Failed to prefetch frame {}: {}", frame_idx, e);
                                    break; // Stop on error
                                }
                            }
                        }
                    }
                    PrefetchMessage::Stop => {
                        info!("Prefetch thread stopping");
                        break;
                    }
                }
            }
        });

        Ok(handle)
    }

    /// Get a frame texture from cache
    ///
    /// Returns:
    /// - Cache hit: texture instantly (0-1ms)
    /// - Cache miss: decode + cache + prefetch (2-10ms)
    pub fn get_frame(&mut self, frame_idx: usize) -> Result<Arc<wgpu::Texture>> {
        info!("Getting frame {} from cache", frame_idx);

        // Update read pattern
        self.update_read_pattern(frame_idx);

        // Check cache
        {
            let mut cache_guard = self.cache.lock().unwrap();
            if let Some(texture) = cache_guard.get(&frame_idx) {
                info!("Cache hit for frame {}", frame_idx);
                return Ok(Arc::clone(texture));
            }
        }

        info!("Cache miss for frame {}, decoding...", frame_idx);

        // Decode frame (hardware-accelerated)
        let mut decoder = HardwareDecoder::new(&self.mkv_path)?;
        let texture = decoder.decode_frame_to_texture(&self.wgpu_device, &self.wgpu_queue, frame_idx)?;
        let texture_arc = Arc::new(texture);

        // Insert into cache
        {
            let mut cache_guard = self.cache.lock().unwrap();
            cache_guard.put(frame_idx, Arc::clone(&texture_arc));
        }

        // Trigger prefetch for next frames
        self.trigger_prefetch(frame_idx);

        Ok(texture_arc)
    }

    /// Update read pattern for prediction
    fn update_read_pattern(&mut self, frame_idx: usize) {
        self.read_pattern.push_back(frame_idx);

        // Keep only last N reads
        if self.read_pattern.len() > 10 {
            self.read_pattern.pop_front();
        }
    }

    /// Predict next frames and trigger prefetch
    fn trigger_prefetch(&mut self, current_frame: usize) {
        // Simple prediction: next N sequential frames
        let start_frame = current_frame + 1;

        if let Some(tx) = &self.prefetch_tx {
            if tx
                .try_send(PrefetchMessage::Prefetch {
                    start_frame,
                    count: self.config.prefetch_depth,
                })
                .is_err()
            {
                warn!("Prefetch channel full, skipping prefetch");
            }
        }
    }

    /// Get cache statistics
    pub fn cache_stats(&self) -> CacheStats {
        let cache_guard = self.cache.lock().unwrap();
        CacheStats {
            size: cache_guard.len(),
            capacity: cache_guard.cap().get(),
            hit_rate: 0.0, // TODO: Track hits/misses
        }
    }

    /// Get cache hit rate
    pub fn hit_rate(&self) -> f64 {
        // TODO: Implement hit/miss tracking
        0.0
    }
}

impl Drop for CacheManager {
    fn drop(&mut self) {
        // Stop prefetch thread
        if let Some(tx) = &self.prefetch_tx {
            let _ = tx.send(PrefetchMessage::Stop);
        }

        // Wait for thread to finish
        if let Some(handle) = self.prefetch_thread.take() {
            let _ = handle.join();
        }
    }
}

/// Cache statistics
#[derive(Debug, Clone)]
pub struct CacheStats {
    /// Current cache size (in frames)
    pub size: usize,

    /// Maximum cache capacity (in frames)
    pub capacity: usize,

    /// Cache hit rate (0.0 to 1.0)
    pub hit_rate: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore] // Requires actual MKV file
    fn test_cache_manager_init() {
        let config = CacheConfig::default();
        let cache_manager = CacheManager::new("test.mkv", config);
        assert!(cache_manager.is_ok());
    }

    #[test]
    fn test_cache_config_default() {
        let config = CacheConfig::default();
        assert_eq!(config.prefetch_depth, 20);
        assert_eq!(config.max_cache_size, 50);
    }
}