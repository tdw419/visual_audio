# Phase 3 Implementation Roadmap - virtio_pixel_rs

## Status: Skeleton Complete (Phase 2)

Current state:
- ✅ lib.rs: SpatialMkvExtractor skeleton compiles
- ✅ backend.rs: VirtioPixelServer vhost-user protocol skeleton compiles
- ✅ main.rs: Entry point wired up
- ⏳ All handlers stubbed (return zeros)
- ⏳ Memory table parsing not implemented
- ⏳ Virtqueue request processing not implemented
- ⏳ MKV extraction not implemented

## Phase 3: Iterative Population

### Step 1: Memory Region Parsing (backend.rs)
**File**: `src/backend.rs` - `handle_set_mem_table()`

Implement:
- Parse VhostUserMemoryRegion array from payload:
  ```rust
  struct VhostUserMemoryRegion {
      guest_phys_addr: u64,
      memory_size: u64,
      userspace_addr: u64,
      mmap_offset: u64,
  }
  ```
- Mmap each region with FD passing (recvmsg)
- Store regions for GPA → host translation
- Update GuestMemory struct

**Verification**: SET_MEM_TABLE handler logs region count + addresses

### Step 2: VirtQueue State Tracking (backend.rs)
**Files**: `src/backend.rs` - `handle_set_vring_*()`

Implement:
- Parse descriptor table address (SET_VRING_ADDR)
- Parse avail ring address
- Parse used ring address
- Store VirtQueue state:
  ```rust
  struct VirtQueue {
      num: u32,
      desc: u64,
      avail: u64,
      used: u64,
      last_avail_idx: u16,
  }
  ```
- Parse queue size (SET_VRING_NUM)
- Parse base index (SET_VRING_BASE)

**Verification**: Log queue setup after SET_VRING_KICK

### Step 3: VirtQueue Request Processing (backend.rs)
**File**: `src/backend.rs` - `handle_set_vring_kick()`

Implement:
- Poll avail ring for new requests (check idx changes)
- Parse descriptor chain (follow NEXT flag)
- Extract VirtIOBlockRequest (16-byte header):
  ```rust
  struct VirtIOBlockRequest {
      type: u32,      // 0=READ, 1=WRITE
      ioprio: u32,
      sector: u64,
  }
  ```
- Extract data buffer GPA and length from chain
- Extract status byte GPA from chain

**Verification**: Log request type, sector, data_len

### Step 4: Guest Memory Access (backend.rs)
**File**: `src/backend.rs` - GuestMemory implementation

Implement:
- GPA translation: find region containing address
- Read bytes from mmap'ed region at offset
- Write bytes to mmap'ed region at offset
- Helper methods:
  ```rust
  fn read_guest_memory(&self, gpa: u64, len: usize) -> Vec<u8>
  fn write_guest_memory(&self, gpa: u64, data: &[u8]) -> Result<()>
  ```

**Verification**: Test with known pattern (write 0xDEADBEEF, read back)

### Step 5: SpatialMkvExtractor Implementation (lib.rs)
**File**: `src/lib.rs` - SpatialMkvExtractor

Implement:
- Wire up va_container for MKV parsing
  ```toml
  # Add to Cargo.toml dependencies
  va_container = { path = "../../va_container_rs" }
  ```
- Implement Hilbert decode:
  - byte i → RGB pixel at [3i, 3i+3)
  - Use existing pixel_build::decode_pixels_to_bytes from Python
- Streaming extraction:
  - Decode only requested sector range
  - No full 2.4GB decode

**Verification**: Extract known sector, compare with Python backend

### Step 6: Block Request Handling (backend.rs)
**File**: `src/backend.rs` - `_handle_block_request()`

Implement:
- READ: `extractor.read(sector * 512, len)`
- WRITE: `extractor.write(sector * 512, data)` (stub read-only warning)
- Write data to guest memory (READ case)
- Write status byte `VIRTIO_BLK_S_OK` to status_gpa
- Update used ring:
  ```rust
  struct VringUsedElem {
      id: u32,
      len: u32,
  }
  ```

**Verification**: Boot reaches early kernel messages

### Step 7: FD Passing Support (backend.rs)
**File**: `src/backend.rs` - message receiving

Implement:
- Use `nix::sys::socket::recvmsg` for ancillary data (FDs)
- Parse file descriptors from SET_MEM_TABLE payload
- Close FDs on cleanup

**Dependency**:
```toml
# Add to Cargo.toml
nix = "0.28"
```

**Verification**: SET_MEM_TABLE successfully mmaps regions

### Step 8: Loop / Thread for VirtQueue Processing (backend.rs)
**File**: `src/backend.rs` - VirtioPixelServer

Implement:
- Spawn thread on SET_VRING_KICK
- Loop: poll avail ring → process request → update used ring
- Use atomic flag for shutdown
- Handle multiple in-flight requests

**Verification**: Continuous I/O throughput measured

### Step 9: Testing & Verification

Implement tests:
- Unit tests for GPA translation
- Unit tests for descriptor chain parsing
- Integration test with mock QEMU client
- Full boot test with real QEMU

## Dependencies to Add

```toml
[dependencies]
# Existing
vhost-user-backend = "0.13"
vhost = { version = "0.11", features = ["vhost-user-backend"] }
virtio-queue = "0.12"
vm-memory = "0.14"
wgpu = "0.20"
pollster = "0.3"
tokio = { version = "1.35", features = ["full"] }
thiserror = "1.0"
anyhow = "1.0"
log = "0.4"
env_logger = "0.11"
memmap2 = "0.9"

# New for Phase 3
nix = "0.28"  # FD passing, recvmsg
numpy = "0.20"  # For Hilbert decode (if using Python bridge)
# OR implement Hilbert decode in pure Rust
```

## Reference Implementation

Python backend with all features:
- `tools/virtio_pixel_vhost.py` (555 lines, 29KB)
- Complete vhost-user protocol
- Memory region mapping via FD passing
- Virtqueue descriptor parsing
- Block request handling
- Spatial MKV extraction

## Success Criteria

- ✅ Compiles without warnings
- ✅ Passes unit tests for GPA translation
- ✅ Passes unit tests for descriptor parsing
- ✅ SET_MEM_TABLE successfully mmaps regions
- ✅ SET_VRING_* handlers parse and store state
- ✅ Virtqueue processor handles READ requests
- ✅ Extracts pixel data from MKV
- ✅ QEMU boots Ubuntu Desktop from spatial storage
- ✅ Throughput measured vs Python backend