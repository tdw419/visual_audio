use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::os::unix::io::{AsRawFd, FromRawFd};

use anyhow::Result;
use log::{error, info, warn};
use nix::sys::socket::{recvmsg, ControlMessageOwned, MsgFlags};
use nix::unistd::{dup, write};
use std::os::fd::OwnedFd;

use super::SpatialMkvExtractor;

/// QEMU memory region descriptor from SET_MEM_TABLE
#[derive(Debug, Clone)]
pub struct VhostUserMemoryRegion {
    pub guest_phys_addr: u64,
    pub memory_size: u64,
    pub userspace_addr: u64,
    pub mmap_offset: u64,
}

/// Mapped QEMU memory region (mutable)
#[derive(Debug)]
pub struct MemoryRegion {
    pub region: VhostUserMemoryRegion,
    pub mmap: memmap2::MmapMut,
    pub guest_phys_base: u64,
    pub size: u64,
}

/// Guest memory with GPA translation
#[derive(Debug)]
pub struct GuestMemory {
    regions: Vec<MemoryRegion>,
}

/// VirtIO virtqueue state
#[derive(Debug)]
pub struct VirtQueue {
    pub num: u32,            // queue size
    pub desc: u64,           // descriptor table guest physical address
    pub avail: u64,          // available ring guest physical address
    pub used: u64,           // used ring guest physical address
    pub ready: bool,         // queue is ready to process
    pub last_avail_idx: u16, // last processed available index
    pub last_used_idx: u16,  // last used index written
    pub avail_addr: u64,     // Full avail ring GPA (for idx access)
    pub call_fd: Option<OwnedFd>, // eventfd for signaling QEMU on completion
}

impl Default for VirtQueue {
    fn default() -> Self {
        Self {
            num: 0,
            desc: 0,
            avail: 0,
            used: 0,
            ready: false,
            last_avail_idx: 0,
            last_used_idx: 0,
            avail_addr: 0,
            call_fd: None,
        }
    }
}

/// VirtIO descriptor (16 bytes)
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct VirtqDesc {
    pub addr: u64,   // Guest physical address of buffer
    pub len: u32,    // Length of buffer
    pub flags: u16,  // VRING_DESC_F_NEXT, VRING_DESC_F_WRITE, etc.
    pub next: u16,   // Next descriptor index if VRING_DESC_F_NEXT
}

// Descriptor flags
pub const VRING_DESC_F_NEXT: u16 = 1;
pub const VRING_DESC_F_WRITE: u16 = 2;
pub const VRING_DESC_F_INDIRECT: u16 = 4;

/// VirtIO available ring (minimum layout)
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct VirtqAvail {
    pub flags: u16,
    pub idx: u16,  // Guest writes this when adding new descriptors
    // ring[]: [u16; N]  // Starts at offset 4
    // used_event: u16   // Only if VIRTIO_F_EVENT_IDX
}

/// VirtIO used element (8 bytes)
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct VirtqUsedElem {
    pub id: u32,   // Descriptor head index
    pub len: u32,  // Bytes written by device
}

/// VirtIO used ring
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct VirtqUsed {
    pub flags: u16,
    pub idx: u16,  // Device writes this when completing requests
    // ring[]: [VirtqUsedElem; N]  // Starts at offset 4
    // avail_event: u16   // Only if VIRTIO_F_EVENT_IDX
}

/// VirtIO block request header (16 bytes)
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct VirtioBlkReq {
    pub r#type: u32,  // VIRTIO_BLK_T_IN=0 (read), VIRTIO_BLK_T_OUT=1 (write)
    pub ioprio: u32,  // I/O priority (unused)
    pub sector: u64,  // Sector number on disk
}

// Block request types
pub const VIRTIO_BLK_T_IN: u32 = 0;
pub const VIRTIO_BLK_T_OUT: u32 = 1;
pub const VIRTIO_BLK_T_FLUSH: u32 = 4;

// Block status codes
pub const VIRTIO_BLK_S_OK: u8 = 0;
pub const VIRTIO_BLK_S_IOERR: u8 = 1;
pub const VIRTIO_BLK_S_UNSUPP: u8 = 2;

impl GuestMemory {
    pub fn new() -> Self {
        Self {
            regions: Vec::new(),
        }
    }

    pub fn add_region(&mut self, region: VhostUserMemoryRegion, mmap: memmap2::MmapMut) {
        let guest_phys_base = region.guest_phys_addr;
        let size = region.memory_size;
        info!(
            "Added memory region: GPA 0x{:x} size {} MB",
            guest_phys_base,
            size / (1024 * 1024)
        );
        self.regions.push(MemoryRegion {
            region,
            mmap,
            guest_phys_base,
            size,
        });
    }

    /// Translate guest physical address to host memory offset
    pub fn translate(&self, gpa: u64) -> Option<(usize, usize)> {
        for mr in &self.regions {
            let offset = gpa.wrapping_sub(mr.guest_phys_base);
            if offset < mr.size {
                return Some((mr.guest_phys_base as usize, offset as usize));
            }
        }
        None
    }

    /// Read from guest physical address
    pub fn read(&self, gpa: u64, len: usize) -> Result<Vec<u8>> {
        if let Some((base, offset)) = self.translate(gpa) {
            for mr in &self.regions {
                if mr.guest_phys_base as usize == base {
                    let end = offset + len;
                    if end <= mr.mmap.len() {
                        return Ok(mr.mmap[offset..end].to_vec());
                    }
                }
            }
        }
        Err(anyhow::anyhow!("GPA 0x{:x} out of range", gpa))
    }

    /// Write to guest physical address
    pub fn write(&mut self, gpa: u64, data: &[u8]) -> Result<()> {
        if let Some((base, offset)) = self.translate(gpa) {
            for mr in &mut self.regions {
                if mr.guest_phys_base as usize == base {
                    let end = offset + data.len();
                    if end <= mr.mmap.len() {
                        mr.mmap[offset..end].copy_from_slice(data);
                        return Ok(());
                    }
                }
            }
        }
        Err(anyhow::anyhow!("GPA 0x{:x} out of range", gpa))
    }
}

/// Simple vhost-user-blk server that handles the protocol manually
pub struct VirtioPixelServer {
    extractor: Arc<Mutex<SpatialMkvExtractor>>,
    socket_path: PathBuf,
    guest_memory: GuestMemory,
    queues: Vec<VirtQueue>,
    running: bool,
}

impl VirtioPixelServer {
    pub fn new(extractor: Arc<Mutex<SpatialMkvExtractor>>, socket_path: PathBuf) -> Self {
        Self {
            extractor,
            socket_path,
            guest_memory: GuestMemory::new(),
            queues: Vec::new(),
            running: false,
        }
    }

    pub fn run(&mut self) -> Result<()> {
        // Remove old socket if exists
        if self.socket_path.exists() {
            std::fs::remove_file(&self.socket_path)?;
        }

        // Create Unix domain socket
        let listener = std::os::unix::net::UnixListener::bind(&self.socket_path)?;
        info!("Listening on {}", self.socket_path.display());

        self.running = true;

        // Accept QEMU connection
        let (mut stream, _addr) = listener.accept()?;
        info!("QEMU connected!");

        // Handle vhost-user protocol messages
        while self.running {
            if let Err(e) = self.handle_message(&mut stream) {
                error!("Error handling message: {}", e);
                break;
            }
        }

        info!("Backend stopped");
        Ok(())
    }

    fn handle_message(&mut self, stream: &mut std::os::unix::net::UnixStream) -> Result<()> {
        let mut hdr_buf = [0u8; 24];

        // Check request type first to see if we need FD passing
        stream.read_exact(&mut hdr_buf)?;
        let request = u32::from_le_bytes([hdr_buf[0], hdr_buf[1], hdr_buf[2], hdr_buf[3]]);

        // Check request type to see if we need FD passing
        // SET_MEM_TABLE (15) and SET_VRING_CALL (10) use FD passing
        let (payload, fds) = if request == 15 || request == 10 {
            // Use recvmsg to get FDs via SCM_RIGHTS
            let mut buf = [0u8; 2048];
            let mut iov = [std::io::IoSliceMut::new(&mut buf)];

            // Calculate cmsg buffer size: one SCM_RIGHTS with up to 8 FDs
            let cmsg_buf_size = 16 + (8 * 4);
            let mut cmsg_buf = vec![0u8; cmsg_buf_size];

            let msg: nix::sys::socket::RecvMsg<nix::sys::socket::UnixAddr> = recvmsg(
                stream.as_raw_fd(),
                &mut iov,
                Some(&mut cmsg_buf),
                MsgFlags::empty(),
            )?;

            // Extract FDs from control messages
            let mut recv_fds = Vec::new();
            for cmsg in msg.cmsgs() {
                if let ControlMessageOwned::ScmRights(scn_fds) = cmsg {
                    recv_fds.extend(scn_fds);
                }
            }

            // Reconstruct payload from buffer (after 24-byte header)
            let size = u64::from_le_bytes([
                hdr_buf[8],
                hdr_buf[9],
                hdr_buf[10],
                hdr_buf[11],
                hdr_buf[12],
                hdr_buf[13],
                hdr_buf[14],
                hdr_buf[15],
            ]) as usize;

            let mut full_payload = vec![0u8; size];
            let copy_len = size.min(msg.bytes.saturating_sub(24));
            if copy_len > 0 && msg.bytes >= 24 {
                full_payload[0..copy_len].copy_from_slice(&buf[24..24 + copy_len]);
            }

            // Read remaining payload if truncated
            if copy_len < size {
                stream.read_exact(&mut full_payload[copy_len..])?;
            }

            (full_payload, recv_fds)
        } else {
            // Simple read for non-FD messages
            let _flags = u32::from_le_bytes([hdr_buf[4], hdr_buf[5], hdr_buf[6], hdr_buf[7]]);
            let size = u64::from_le_bytes([
                hdr_buf[8],
                hdr_buf[9],
                hdr_buf[10],
                hdr_buf[11],
                hdr_buf[12],
                hdr_buf[13],
                hdr_buf[14],
                hdr_buf[15],
            ]) as usize;

            let mut payload = vec![0u8; size];
            if size > 0 {
                stream.read_exact(&mut payload)?;
            }

            (payload, vec![])
        };

        let _flags = u32::from_le_bytes([hdr_buf[4], hdr_buf[5], hdr_buf[6], hdr_buf[7]]);
        let size = payload.len() as u64;

        info!(
            "VhostUser message: request={} size={} fds={}",
            request,
            size,
            fds.len()
        );

        // Handle message type (FDs for SET_MEM_TABLE and SET_VRING_CALL)
        let (reply, _call_fds) = match request {
            1 => (self.handle_set_owner(&payload)?, vec![]),
            2 => (self.handle_reset_owner(&payload)?, vec![]),
            3 => (self.handle_get_features(&payload)?, vec![]),
            4 => (self.handle_set_features(&payload)?, vec![]),
            5 => (self.handle_set_vring_num(&payload)?, vec![]),
            6 => (self.handle_set_vring_addr(&payload)?, vec![]),
            7 => (self.handle_set_vring_base(&payload)?, vec![]),
            8 => (self.handle_get_vring_base(&payload)?, vec![]),
            9 => (self.handle_set_vring_kick(&payload)?, vec![]),
            10 => self.handle_set_vring_call(&payload, &fds)?,
            11 => (self.handle_set_vring_err(&payload)?, vec![]),
            15 => self.handle_set_mem_table(&payload, &fds)?,
            _ => {
                warn!("Unsupported message type: {}", request);
                (vec![0u8; 24], vec![])
            }
        };

        // Close FDs after use (except call FDs which are stored in queues)
        for fd in fds {
            let _ = nix::unistd::close(fd);
        }

        // Send reply
        stream.write_all(&reply)?;

        Ok(())
    }

    fn handle_set_owner(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        info!("SET_OWNER");
        Ok(vec![0u8; 24])
    }

    fn handle_reset_owner(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        info!("RESET_OWNER");
        Ok(vec![0u8; 24])
    }

    fn handle_get_features(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        info!("GET_FEATURES");
        // Return 8 bytes of features (read-only)
        let features = 1u64 << 5; // VIRTIO_BLK_F_RO
        let mut reply = [0u8; 32];
        reply[0..24].copy_from_slice(&[0u8; 24]); // Header
        reply[24..32].copy_from_slice(&features.to_le_bytes());
        Ok(reply.to_vec())
    }

    fn handle_set_features(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        info!("SET_FEATURES");
        Ok(vec![0u8; 24])
    }

    fn handle_set_vring_num(&mut self, payload: &[u8]) -> Result<Vec<u8>> {
        let idx = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);
        let num = u32::from_le_bytes([payload[4], payload[5], payload[6], payload[7]]);
        info!("SET_VRING_NUM: index={} num={}", idx, num);

        while self.queues.len() <= idx as usize {
            self.queues.push(VirtQueue::default());
        }
        self.queues[idx as usize].num = num;

        Ok(vec![0u8; 24])
    }

    fn handle_set_vring_addr(&mut self, payload: &[u8]) -> Result<Vec<u8>> {
        let idx = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);
        let flags = u32::from_le_bytes([payload[4], payload[5], payload[6], payload[7]]);
        let desc = u64::from_le_bytes([
            payload[8],
            payload[9],
            payload[10],
            payload[11],
            payload[12],
            payload[13],
            payload[14],
            payload[15],
        ]);
        let avail = u64::from_le_bytes([
            payload[24],
            payload[25],
            payload[26],
            payload[27],
            payload[28],
            payload[29],
            payload[30],
            payload[31],
        ]);
        let used = u64::from_le_bytes([
            payload[40],
            payload[41],
            payload[42],
            payload[43],
            payload[44],
            payload[45],
            payload[46],
            payload[47],
        ]);

        info!(
            "SET_VRING_ADDR: index={} flags={} desc=0x{:x} avail=0x{:x} used=0x{:x}",
            idx, flags, desc, avail, used
        );

        if self.queues.len() > idx as usize {
            self.queues[idx as usize].desc = desc;
            self.queues[idx as usize].avail = avail;
            self.queues[idx as usize].used = used;
        }

        Ok(vec![0u8; 24])
    }

    fn handle_set_vring_base(&mut self, payload: &[u8]) -> Result<Vec<u8>> {
        let idx = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);
        let base = u64::from_le_bytes([
            payload[8],
            payload[9],
            payload[10],
            payload[11],
            payload[12],
            payload[13],
            payload[14],
            payload[15],
        ]);

        info!("SET_VRING_BASE: index={} base={}", idx, base);

        if self.queues.len() > idx as usize {
            self.queues[idx as usize].last_avail_idx = base as u16;
        }

        Ok(vec![0u8; 24])
    }

    fn handle_get_vring_base(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        info!("GET_VRING_BASE");
        // Return 8 bytes (last_avail_idx)
        let mut reply = [0u8; 32];
        reply[0..24].copy_from_slice(&[0u8; 24]); // Header
        reply[24..32].copy_from_slice(&0u64.to_le_bytes());
        Ok(reply.to_vec())
    }

    fn handle_set_vring_kick(&mut self, _payload: &[u8]) -> Result<Vec<u8>> {
        info!("SET_VRING_KICK");
        // Poll virtqueue 0 for new requests
        if let Err(e) = self.poll_virtqueue(0) {
            error!("Error polling virtqueue: {}", e);
        }
        Ok(vec![0u8; 24])
    }

    fn handle_set_vring_call(&mut self, payload: &[u8], fds: &[std::os::fd::RawFd]) -> Result<(Vec<u8>, Vec<std::os::fd::RawFd>)> {
        let idx = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);
        let flags = u32::from_le_bytes([payload[4], payload[5], payload[6], payload[7]]);

        info!(
            "SET_VRING_CALL: index={} flags={} fds={}",
            idx,
            flags,
            fds.len()
        );

        // Store the callfd (eventfd for signaling QEMU)
        if !fds.is_empty() {
            let fd = fds[0];
            info!("  Storing callfd={} for queue {}", fd, idx);
            let owned_fd = unsafe { OwnedFd::from_raw_fd(dup(fd)?) };

            while self.queues.len() <= idx as usize {
                self.queues.push(VirtQueue::default());
            }
            self.queues[idx as usize].call_fd = Some(owned_fd);
        } else {
            warn!("  No FD passed in SET_VRING_CALL");
        }

        // Return reply and empty FDs list (we're keeping the callfd)
        Ok((vec![0u8; 24], vec![]))
    }

    fn handle_set_vring_err(&self, _payload: &[u8]) -> Result<Vec<u8>> {
        info!("SET_VRING_ERR");
        Ok(vec![0u8; 24])
    }

    fn handle_set_mem_table(
        &mut self,
        payload: &[u8],
        fds: &[std::os::fd::RawFd],
    ) -> Result<(Vec<u8>, Vec<std::os::fd::RawFd>)> {
        let num_regions = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);
        let padding = u32::from_le_bytes([payload[4], payload[5], payload[6], payload[7]]);

        info!(
            "SET_MEM_TABLE: {} regions (padding={}) fds={}",
            num_regions,
            padding,
            fds.len()
        );

        // Each region is 32 bytes (4x u64)
        let mut regions = Vec::new();
        for i in 0..num_regions as usize {
            let offset = 8 + i * 32;
            let region = VhostUserMemoryRegion {
                guest_phys_addr: u64::from_le_bytes([
                    payload[offset],
                    payload[offset + 1],
                    payload[offset + 2],
                    payload[offset + 3],
                    payload[offset + 4],
                    payload[offset + 5],
                    payload[offset + 6],
                    payload[offset + 7],
                ]),
                memory_size: u64::from_le_bytes([
                    payload[offset + 8],
                    payload[offset + 9],
                    payload[offset + 10],
                    payload[offset + 11],
                    payload[offset + 12],
                    payload[offset + 13],
                    payload[offset + 14],
                    payload[offset + 15],
                ]),
                userspace_addr: u64::from_le_bytes([
                    payload[offset + 16],
                    payload[offset + 17],
                    payload[offset + 18],
                    payload[offset + 19],
                    payload[offset + 20],
                    payload[offset + 21],
                    payload[offset + 22],
                    payload[offset + 23],
                ]),
                mmap_offset: u64::from_le_bytes([
                    payload[offset + 24],
                    payload[offset + 25],
                    payload[offset + 26],
                    payload[offset + 27],
                    payload[offset + 28],
                    payload[offset + 29],
                    payload[offset + 30],
                    payload[offset + 31],
                ]),
            };

            info!(
                "  Region {}: GPA 0x{:x} size {}MB userspace 0x{:x} mmap_offset 0x{:x}",
                i,
                region.guest_phys_addr,
                region.memory_size / (1024 * 1024),
                region.userspace_addr,
                region.mmap_offset
            );

            regions.push(region);
        }

        // Mmap regions using received FDs
        for (i, region) in regions.iter().enumerate() {
            if i < fds.len() {
                let fd = fds[i];
                let mmap_size = region.memory_size as usize;
                let mmap_offset = region.mmap_offset as usize;

                info!(
                    "  Mmaping region {} with fd={} size={}MB offset=0x{:x}",
                    i,
                    fd,
                    mmap_size / (1024 * 1024),
                    mmap_offset
                );

                // Convert raw FD to OwnedFd for safe ownership
                let owned_fd = unsafe { OwnedFd::from_raw_fd(dup(fd)?) };

                // mmap the region with the received FD
                let mmap = unsafe {
                    memmap2::MmapOptions::new()
                        .len(mmap_size)
                        .offset(mmap_offset as u64)
                        .map_mut(&owned_fd)?
                };

                self.guest_memory.add_region(region.clone(), mmap);
            } else {
                warn!(
                    "  Region {} has no associated FD (have {}, need {})",
                    i,
                    fds.len(),
                    regions.len()
                );
            }
        }

        info!(
            "SET_MEM_TABLE: mmap'd {} regions into GuestMemory",
            self.guest_memory.regions.len()
        );

        // Return reply and empty FDs list (we're keeping the mem FDs in the mmap)
        Ok((vec![0u8; 24], vec![]))
    }

    /// Read a VirtIO descriptor from guest memory
    fn read_descriptor(&self, queue_idx: usize, desc_idx: u16) -> Result<VirtqDesc> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        let queue = &self.queues[queue_idx];
        let desc_gpa = queue.desc + (desc_idx as u64) * 16; // VirtqDesc is 16 bytes

        let desc_bytes = self.guest_memory.read(desc_gpa, 16)?;
        if desc_bytes.len() < 16 {
            return Err(anyhow::anyhow!("Descriptor read truncated at GPA 0x{:x}", desc_gpa));
        }

        let addr = u64::from_le_bytes([
            desc_bytes[0],
            desc_bytes[1],
            desc_bytes[2],
            desc_bytes[3],
            desc_bytes[4],
            desc_bytes[5],
            desc_bytes[6],
            desc_bytes[7],
        ]);
        let len = u32::from_le_bytes([
            desc_bytes[8],
            desc_bytes[9],
            desc_bytes[10],
            desc_bytes[11],
        ]);
        let flags = u16::from_le_bytes([
            desc_bytes[12],
            desc_bytes[13],
        ]);
        let next = u16::from_le_bytes([
            desc_bytes[14],
            desc_bytes[15],
        ]);

        Ok(VirtqDesc {
            addr,
            len,
            flags,
            next,
        })
    }

    /// Read available ring idx from guest memory (at avail_gpa + 2)
    fn read_avail_idx(&self, queue_idx: usize) -> Result<u16> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        let queue = &self.queues[queue_idx];
        let idx_gpa = queue.avail + 2; // avail.idx is at offset 2

        let idx_bytes = self.guest_memory.read(idx_gpa, 2)?;
        if idx_bytes.len() < 2 {
            return Err(anyhow::anyhow!("avail.idx read truncated at GPA 0x{:x}", idx_gpa));
        }

        let idx = u16::from_le_bytes([idx_bytes[0], idx_bytes[1]]);
        Ok(idx)
    }

    /// Read descriptor head from avail.ring[]
    fn read_avail_ring_entry(&self, queue_idx: usize, idx: u16) -> Result<u16> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        let queue = &self.queues[queue_idx];
        let num = queue.num as u16;
        let ring_idx = (idx % num) as usize;
        let ring_gpa = queue.avail + 4 + (ring_idx as u64) * 2; // avail.ring starts at offset 4

        let entry_bytes = self.guest_memory.read(ring_gpa, 2)?;
        if entry_bytes.len() < 2 {
            return Err(anyhow::anyhow!(
                "avail.ring[{}] read truncated at GPA 0x{:x}",
                ring_idx,
                ring_gpa
            ));
        }

        let head = u16::from_le_bytes([entry_bytes[0], entry_bytes[1]]);
        Ok(head)
    }

    /// Write used element to guest memory
    fn write_used_elem(&mut self, queue_idx: usize, head: u16, len: u32) -> Result<()> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        let queue = &mut self.queues[queue_idx];
        let num = queue.num as u16;
        let used_idx = queue.last_used_idx;
        let ring_idx = (used_idx % num) as usize;
        let ring_gpa = queue.used + 4 + (ring_idx as u64) * 8; // used.ring starts at offset 4

        // Write VirtqUsedElem (8 bytes)
        let mut elem_bytes = [0u8; 8];
        elem_bytes[0..4].copy_from_slice(&(head as u32).to_le_bytes());
        elem_bytes[4..8].copy_from_slice(&len.to_le_bytes());
        self.guest_memory.write(ring_gpa, &elem_bytes)?;

        // Update used.idx
        let idx_gpa = queue.used + 2;
        let new_idx = used_idx.wrapping_add(1);
        queue.last_used_idx = new_idx;
        let idx_bytes = new_idx.to_le_bytes();
        self.guest_memory.write(idx_gpa, &idx_bytes)?;

        Ok(())
    }

    /// Poll virtqueue for new requests and process them
    fn poll_virtqueue(&mut self, queue_idx: usize) -> Result<()> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        let queue = &self.queues[queue_idx];
        if !queue.ready {
            return Ok(());
        }

        // Check if new descriptors available
        let avail_idx = self.read_avail_idx(queue_idx)?;
        let last_avail = self.queues[queue_idx].last_avail_idx;

        if avail_idx == last_avail {
            return Ok(()); // No new requests
        }

        let num_new = avail_idx.wrapping_sub(last_avail);
        info!(
            "Queue {} has {} new requests (avail_idx={}, last_avail={})",
            queue_idx, num_new, avail_idx, last_avail
        );

        // Process each new descriptor
        for _ in 0..num_new {
            let req_idx = self.queues[queue_idx].last_avail_idx;
            let head = self.read_avail_ring_entry(queue_idx, req_idx)?;

            info!("Processing request {} with descriptor head {}", req_idx, head);

            // Walk descriptor chain (Header → Data → Status)
            let descriptors = self.walk_descriptor_chain(queue_idx, head)?;

            // Handle VirtIO block request
            self.handle_virtio_block_request(&descriptors)?;
            // Complete request (write used ring)
            self.write_used_elem(queue_idx, head, 0)?;

            // Advance avail_idx
            self.queues[queue_idx].last_avail_idx =
                self.queues[queue_idx].last_avail_idx.wrapping_add(1);
        }

        // Signal QEMU that requests are complete
        self.trigger_callfd(queue_idx)?;

        Ok(())
    }

    /// Walk descriptor chain and return all descriptors in order
    fn walk_descriptor_chain(&self, queue_idx: usize, head: u16) -> Result<Vec<VirtqDesc>> {
        let mut descriptors = Vec::new();
        let mut desc_idx = head;
        let mut seen = std::collections::HashSet::new();

        loop {
            if seen.contains(&desc_idx) {
                return Err(anyhow::anyhow!("Descriptor cycle detected at idx {}", desc_idx));
            }
            seen.insert(desc_idx);

            let desc = self.read_descriptor(queue_idx, desc_idx)?;
            descriptors.push(desc);

            if desc.flags & VRING_DESC_F_NEXT == 0 {
                break;
            }
            desc_idx = desc.next;
        }

        Ok(descriptors)
    }

    /// Signal QEMU that requests are complete via callfd eventfd
    fn trigger_callfd(&mut self, queue_idx: usize) -> Result<()> {
        if queue_idx >= self.queues.len() {
            return Err(anyhow::anyhow!("Invalid queue index {}", queue_idx));
        }

        if let Some(call_fd) = &self.queues[queue_idx].call_fd {
            // Write 1 to eventfd to wake up QEMU
            let val = 1u64.to_ne_bytes();
            if let Err(e) = write(call_fd, &val) {
                error!("Failed to trigger callfd for queue {}: {}", queue_idx, e);
            } else {
                info!("Triggered callfd for queue {} (woke QEMU)", queue_idx);
            }
        } else {
            warn!("No callfd set for queue {}", queue_idx);
        }

        Ok(())
    }

    /// Handle VirtIO block request (Header → Data → Status)
    fn handle_virtio_block_request(&mut self, descriptors: &[VirtqDesc]) -> Result<()> {
        // Expect at least 3 descriptors: Header, Data, Status
        if descriptors.len() < 3 {
            return Err(anyhow::anyhow!(
                "Expected 3+ descriptors, got {}",
                descriptors.len()
            ));
        }

        let header_desc = &descriptors[0];
        let data_desc = &descriptors[1];
        let status_desc = &descriptors[2];

        // Read request header
        let header_bytes = self.guest_memory.read(header_desc.addr, header_desc.len as usize)?;
        if header_bytes.len() < 16 {
            return Err(anyhow::anyhow!("Request header truncated"));
        }

        let req_type = u32::from_le_bytes([
            header_bytes[0],
            header_bytes[1],
            header_bytes[2],
            header_bytes[3],
        ]);
        let sector = u64::from_le_bytes([
            header_bytes[8],
            header_bytes[9],
            header_bytes[10],
            header_bytes[11],
            header_bytes[12],
            header_bytes[13],
            header_bytes[14],
            header_bytes[15],
        ]);

        info!(
            "Block request: type={} sector={} data_len={} status_len={}",
            req_type,
            sector,
            data_desc.len,
            status_desc.len
        );

        // Handle read request (T_IN=0)
        if req_type == VIRTIO_BLK_T_IN {
            // Calculate offset in the 7GB decoded data space
            let offset = sector * 512;

            // Extract Hilbert pixels from SpatialMkvExtractor
            let decoded_data = {
                let mut extractor = self.extractor.lock().unwrap();
                extractor.read(offset, data_desc.len as u64)?
            };

            // Write decoded bytes to data buffer
            self.guest_memory.write(data_desc.addr, &decoded_data)?;
            info!(
                "  Extracted {} Hilbert bytes at offset 0x{:x} (sector {})",
                decoded_data.len(), offset, sector
            );
        }

        // Write status OK
        self.guest_memory.write(status_desc.addr, &[VIRTIO_BLK_S_OK])?;
        info!("  Wrote VIRTIO_BLK_S_OK to status byte");

        Ok(())
    }
}