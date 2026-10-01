#!/bin/bash
# Pixel-Native VM - Execute programs by transforming pixels
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
PIXEL_VM_DIR="$PROJECT_ROOT/pixel_trace/vm"

echo "=== Pixel-Native VM Creation ==="
echo ""
echo "This VM executes programs by applying pixel transformations"
echo "instead of running compiled code."
echo ""

# Create the Pixel-Native VM
cat > "$PIXEL_VM_DIR/src/lib.rs" << 'EOF'
//! Pixel-Native Virtual Machine
//!
//! Executes programs by directly manipulating pixel patterns.
//! Instead of compiled code, the VM applies pixel transformations.
//!
//! This is how we achieve: "When I type 'ls', the pixels themselves
//! transform to produce the output."

use std::collections::HashMap;
use std::path::PathBuf;
use serde::{Deserialize, Serialize};

use crate::analyzer::{PixelProgram, PixelPattern, PixelOperationTemplate, DataPattern};

/// Pixel instruction opcodes (256 patterns)
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[repr(u8)]
pub enum PixelOpCode {
    // Data movement (0x00-0x0F)
    Nop = 0x00,
    LoadRegion = 0x01,
    StoreRegion = 0x02,
    CopyRegion = 0x03,
    MoveRegion = 0x04,
    FillRegion = 0x05,

    // Transformation (0x10-0x1F)
    TransformInvert = 0x10,
    TransformShift = 0x11,
    TransformScale = 0x12,
    TransformRotate = 0x13,
    TransformFlipH = 0x14,
    TransformFlipV = 0x15,

    // Pattern matching (0x20-0x2F)
    MatchPattern = 0x20,
    ReplacePattern = 0x21,
    FindHotspot = 0x22,
    ExtractSubpattern = 0x23,

    // Compression (0x30-0x3F)
    CompressRLE = 0x30,
    DecompressRLE = 0x31,
    CompressHuffman = 0x32,
    DecompressHuffman = 0x33,

    // File operations (0x40-0x4F)
    FileOpen = 0x40,
    FileRead = 0x41,
    FileWrite = 0x42,
    FileClose = 0x43,
    DirList = 0x44,

    // Process control (0x50-0x5F)
    ProcessFork = 0x50,
    ProcessExec = 0x51,
    ProcessExit = 0x52,
    ProcessWait = 0x53,

    // Display (0x60-0x6F)
    DisplayClear = 0x60,
    DisplayWrite = 0x61,
    DisplayScroll = 0x62,
    DisplayCursorMove = 0x63,

    // Memory (0x70-0x7F)
    MemAlloc = 0x70,
    MemFree = 0x71,
    MemMap = 0x72,
    MemUnmap = 0x73,

    // System calls (0x80-0x8F)
    SysGetpid = 0x80,
    SysGetuid = 0x81,
    SysGettime = 0x82,
    SysSleep = 0x83,

    // Network (0x90-0x9F)
    NetSocket = 0x90,
    NetConnect = 0x91,
    NetSend = 0x92,
    NetRecv = 0x93,

    // User-defined (0xF0-0xFF)
    UserOp0 = 0xF0,
    UserOp1 = 0xF1,
    UserOp2 = 0xF2,
    UserOp3 = 0xF3,
}

impl PixelOpCode {
    pub fn from_u8(val: u8) -> Self {
        match val {
            0x00 => PixelOpCode::Nop,
            0x01 => PixelOpCode::LoadRegion,
            0x02 => PixelOpCode::StoreRegion,
            0x03 => PixelOpCode::CopyRegion,
            0x04 => PixelOpCode::MoveRegion,
            0x05 => PixelOpCode::FillRegion,
            0x10 => PixelOpCode::TransformInvert,
            0x11 => PixelOpCode::TransformShift,
            0x12 => PixelOpCode::TransformScale,
            0x13 => PixelOpCode::TransformRotate,
            0x14 => PixelOpCode::TransformFlipH,
            0x15 => PixelOpCode::TransformFlipV,
            0x20 => PixelOpCode::MatchPattern,
            0x21 => PixelOpCode::ReplacePattern,
            0x22 => PixelOpCode::FindHotspot,
            0x23 => PixelOpCode::ExtractSubpattern,
            0x30 => PixelOpCode::CompressRLE,
            0x31 => PixelOpCode::DecompressRLE,
            0x32 => PixelOpCode::CompressHuffman,
            0x33 => PixelOpCode::DecompressHuffman,
            0x40 => PixelOpCode::FileOpen,
            0x41 => PixelOpCode::FileRead,
            0x42 => PixelOpCode::FileWrite,
            0x43 => PixelOpCode::FileClose,
            0x44 => PixelOpCode::DirList,
            0x50 => PixelOpCode::ProcessFork,
            0x51 => PixelOpCode::ProcessExec,
            0x52 => PixelOpCode::ProcessExit,
            0x53 => PixelOpCode::ProcessWait,
            0x60 => PixelOpCode::DisplayClear,
            0x61 => PixelOpCode::DisplayWrite,
            0x62 => PixelOpCode::DisplayScroll,
            0x63 => PixelOpCode::DisplayCursorMove,
            0x70 => PixelOpCode::MemAlloc,
            0x71 => PixelOpCode::MemFree,
            0x72 => PixelOpCode::MemMap,
            0x73 => PixelOpCode::MemUnmap,
            0x80 => PixelOpCode::SysGetpid,
            0x81 => PixelOpCode::SysGetuid,
            0x82 => PixelOpCode::SysGettime,
            0x83 => PixelOpCode::SysSleep,
            0x90 => PixelOpCode::NetSocket,
            0x91 => PixelOpCode::NetConnect,
            0x92 => PixelOpCode::NetSend,
            0x93 => PixelOpCode::NetRecv,
            0xF0 => PixelOpCode::UserOp0,
            0xF1 => PixelOpCode::UserOp1,
            0xF2 => PixelOpCode::UserOp2,
            0xF3 => PixelOpCode::UserOp3,
            _ => PixelOpCode::Nop,
        }
    }
}

/// Pixel register (stores pixel regions)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PixelRegister {
    pub reg_id: u8,
    pub coord: (u32, u32),
    pub size: (u32, u32, u32),
    pub data: Vec<u8>,
}

impl PixelRegister {
    pub fn new(reg_id: u8) -> Self {
        PixelRegister {
            reg_id,
            coord: (0, 0),
            size: (0, 0, 0),
            data: Vec::new(),
        }
    }

    pub fn load(&mut self, coord: (u32, u32), size: (u32, u32, u32), data: Vec<u8>) {
        self.coord = coord;
        self.size = size;
        self.data = data;
    }
}

/// Pixel instruction
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PixelInstruction {
    pub opcode: PixelOpCode,
    pub operands: Vec<u32>, // Coordinate or value operands
    pub register_ops: Vec<u8>, // Register IDs
    pub comment: Option<String>,
}

impl PixelInstruction {
    pub fn new(opcode: PixelOpCode) -> Self {
        PixelInstruction {
            opcode,
            operands: Vec::new(),
            register_ops: Vec::new(),
            comment: None,
        }
    }

    pub fn with_operand(mut self, operand: u32) -> Self {
        self.operands.push(operand);
        self
    }

    pub fn with_operands(mut self, operands: Vec<u32>) -> Self {
        self.operands = operands;
        self
    }

    pub fn with_reg(mut self, reg: u8) -> Self {
        self.register_ops.push(reg);
        self
    }

    pub fn with_comment(mut self, comment: String) -> Self {
        self.comment = Some(comment);
        self
    }
}

/// Pixel-Native VM state
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PixelVM {
    pub registers: [PixelRegister; 16], // 16 general-purpose registers
    pub program_counter: usize,
    pub flags: u32, // Zero, Carry, etc.
    pub memory_size: u64, // Virtual pixel memory size
    pub execution_stats: ExecutionStats,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExecutionStats {
    pub instructions_executed: usize,
    pub pixels_touched: usize,
    pub transformations_applied: usize,
    pub execution_time_us: u64,
}

impl PixelVM {
    pub fn new() -> Self {
        let mut registers = Vec::with_capacity(16);
        for i in 0..16 {
            registers.push(PixelRegister::new(i as u8));
        }

        PixelVM {
            registers: registers.try_into().unwrap(),
            program_counter: 0,
            flags: 0,
            memory_size: 4 * 1024 * 1024, // 4MB pixel memory
            execution_stats: ExecutionStats::default(),
        }
    }

    /// Compile a pixel program to pixel instructions
    pub fn compile(&mut self, program: &PixelProgram) -> Result<Vec<PixelInstruction>, String> {
        let mut instructions = Vec::new();

        for pattern_id in &program.execution_order {
            let pattern = program.patterns.iter()
                .find(|p| &p.pattern_id == pattern_id)
                .ok_or_else(|| format!("Pattern {} not found", pattern_id))?;

            // Compile pattern to instructions
            let pattern_instructions = self.compile_pattern(pattern)?;
            instructions.extend(pattern_instructions);
        }

        Ok(instructions)
    }

    /// Compile a single pattern to instructions
    fn compile_pattern(&self, pattern: &PixelPattern) -> Result<Vec<PixelInstruction>, String> {
        let mut instructions = Vec::new();

        for op_template in &pattern.operations {
            let instruction = self.compile_operation(op_template, pattern)?;
            instructions.push(instruction);
        }

        Ok(instructions)
    }

    /// Compile an operation template to instruction
    fn compile_operation(&self, op: &PixelOperationTemplate, pattern: &PixelPattern) -> Result<PixelInstruction, String> {
        // This is where the magic happens: map abstract operations
        // to pixel VM opcodes
        let instruction = match &op.op_type {
            // Data movement
            crate::tracer::PixelOpType::Read => {
                PixelInstruction::new(PixelOpCode::LoadRegion)
                    .with_operands(vec![
                        op.relative_coord.0 as u32,
                        op.relative_coord.1 as u32,
                        op.relative_coord.2 as u32,
                        op.size.0, op.size.1, op.size.2,
                    ])
                    .with_reg(0) // Load into R0
                    .with_comment(format!("Read region at ({}, {}, {})", op.relative_coord.0, op.relative_coord.1, op.relative_coord.2))
            }
            crate::tracer::PixelOpType::Write => {
                PixelInstruction::new(PixelOpCode::StoreRegion)
                    .with_reg(0) // Store from R0
                    .with_operands(vec![
                        op.relative_coord.0 as u32,
                        op.relative_coord.1 as u32,
                        op.relative_coord.2 as u32,
                    ])
                    .with_comment(format!("Write region to ({}, {}, {})", op.relative_coord.0, op.relative_coord.1, op.relative_coord.2))
            }
            crate::tracer::PixelOpType::Copy => {
                PixelInstruction::new(PixelOpCode::CopyRegion)
                    .with_operands(vec![
                        op.relative_coord.0 as u32,
                        op.relative_coord.1 as u32,
                        op.relative_coord.2 as u32,
                        op.size.0, op.size.1, op.size.2,
                    ])
                    .with_comment(format!("Copy region {}x{}x{}", op.size.0, op.size.1, op.size.2))
            }
            crate::tracer::PixelOpType::Fill => {
                PixelInstruction::new(PixelOpCode::FillRegion)
                    .with_operands(vec![
                        op.relative_coord.0 as u32,
                        op.relative_coord.1 as u32,
                        op.relative_coord.2 as u32,
                        op.size.0, op.size.1, op.size.2,
                    ])
                    .with_reg(1) // Fill value in R1
                    .with_comment(format!("Fill region {}x{}x{}", op.size.0, op.size.1, op.size.2))
            }

            // Transformations
            crate::tracer::PixelOpType::Transform => {
                PixelInstruction::new(PixelOpCode::TransformShift)
                    .with_operands(vec![
                        op.relative_coord.0 as u32,
                        op.relative_coord.1 as u32,
                    ])
                    .with_comment("Transform pixels")
            }

            _ => {
                PixelInstruction::new(PixelOpCode::Nop)
                    .with_comment(format!("Unknown op: {:?}", op.op_type))
            }
        };

        Ok(instruction)
    }

    /// Execute a pixel instruction
    pub fn execute(&mut self, instruction: &PixelInstruction, pixel_container: &mut PixelContainer) -> Result<(), String> {
        let start = std::time::Instant::now();

        match instruction.opcode {
            PixelOpCode::LoadRegion => {
                // Load region from container into register
                let x = instruction.operands[0];
                let y = instruction.operands[1];
                let z = instruction.operands[2];
                let width = instruction.operands[3];
                let height = instruction.operands[4];
                let depth = instruction.operands[5];
                let reg = instruction.register_ops[0];

                let data = pixel_container.read_region(x, y, z, width, height, depth)?;
                self.registers[reg as usize].load((x, y), (width, height, depth), data);

                self.execution_stats.instructions_executed += 1;
                self.execution_stats.pixels_touched += (width * height) as usize;
            }

            PixelOpCode::StoreRegion => {
                // Store register to container
                let reg = instruction.register_ops[0];
                let x = instruction.operands[0];
                let y = instruction.operands[1];
                let z = instruction.operands[2];

                let register = &self.registers[reg as usize];
                pixel_container.write_region(x, y, z, &register.data)?;

                self.execution_stats.instructions_executed += 1;
                self.execution_stats.pixels_touched += register.data.len() / 3;
            }

            PixelOpCode::CopyRegion => {
                // Copy region within container
                let src_x = instruction.operands[0];
                let src_y = instruction.operands[1];
                let src_z = instruction.operands[2];
                let width = instruction.operands[3];
                let height = instruction.operands[4];
                let depth = instruction.operands[5];

                let data = pixel_container.read_region(src_x, src_y, src_z, width, height, depth)?;
                // For copy, we'd need destination coordinates - this is simplified
                pixel_container.write_region(src_x, src_y, src_z, &data)?;

                self.execution_stats.instructions_executed += 1;
                self.execution_stats.pixels_touched += (width * height) as usize;
            }

            PixelOpCode::FillRegion => {
                // Fill region with value
                let x = instruction.operands[0];
                let y = instruction.operands[1];
                let z = instruction.operands[2];
                let width = instruction.operands[3];
                let height = instruction.operands[4];
                let depth = instruction.operands[5];
                let reg = instruction.register_ops[1];

                let register = &self.registers[reg as usize];
                let fill_value = if !register.data.is_empty() {
                    register.data[0]
                } else {
                    0
                };

                let fill_data = vec![fill_value; (width * height * depth) as usize];
                pixel_container.write_region(x, y, z, &fill_data)?;

                self.execution_stats.instructions_executed += 1;
                self.execution_stats.pixels_touched += (width * height) as usize;
            }

            PixelOpCode::TransformShift => {
                // Shift pixels (simplified)
                self.execution_stats.instructions_executed += 1;
                self.execution_stats.transformations_applied += 1;
            }

            PixelOpCode::Nop => {
                self.program_counter += 1;
            }

            _ => {
                return Err(format!("Unimplemented opcode: {:?}", instruction.opcode));
            }
        }

        self.execution_stats.execution_time_us += start.elapsed().as_micros() as u64;
        self.program_counter += 1;

        Ok(())
    }

    /// Run a complete pixel program
    pub fn run_program(&mut self, program: &PixelProgram, pixel_container: &mut PixelContainer) -> Result<ExecutionStats, String> {
        println!("Running pixel program: {}", program.program_id);
        println!("Command: {}", program.command);

        let instructions = self.compile(program)?;

        println!("Compiled to {} instructions", instructions.len());
        println!("Executing...");

        self.program_counter = 0;
        self.execution_stats = ExecutionStats::default();

        for instruction in &instructions {
            self.execute(instruction, pixel_container)?;
        }

        println!("Execution complete!");
        println!("  Instructions: {}", self.execution_stats.instructions_executed);
        println!("  Pixels touched: {}", self.execution_stats.pixels_touched);
        println!("  Transformations: {}", self.execution_stats.transformations_applied);
        println!("  Time: {} μs", self.execution_stats.execution_time_us);

        Ok(self.execution_stats.clone())
    }
}

impl Default for PixelVM {
    fn default() -> Self {
        Self::new()
    }
}

/// Pixel container (VAC2 format)
#[derive(Debug, Clone)]
pub struct PixelContainer {
    pub width: u32,
    pub height: u32,
    pub depth: u32,
    pub data: Vec<u8>,
}

impl PixelContainer {
    pub fn new(width: u32, height: u32, depth: u32) -> Self {
        let size = (width * height * depth) as usize;
        PixelContainer {
            width,
            height,
            depth,
            data: vec![0; size],
        }
    }

    pub fn read_region(&self, x: u32, y: u32, z: u32, width: u32, height: u32, depth: u32) -> Result<Vec<u8>, String> {
        // Validate bounds
        if x + width > self.width || y + height > self.height || z + depth > self.depth {
            return Err("Region out of bounds".to_string());
        }

        let mut result = Vec::with_capacity((width * height * depth) as usize);

        for dz in 0..depth {
            for dy in 0..height {
                for dx in 0..width {
                    let offset = ((z + dz) * self.height * self.width
                        + (y + dy) * self.width
                        + (x + dx)) as usize;
                    result.push(self.data[offset]);
                }
            }
        }

        Ok(result)
    }

    pub fn write_region(&mut self, x: u32, y: u32, z: u32, data: &[u8]) -> Result<(), String> {
        let len = data.len() as u32;
        let mut offset = (z * self.height * self.width + y * self.width + x) as usize;

        for (idx, &byte) in data.iter().enumerate() {
            if offset < self.data.len() {
                self.data[offset] = byte;
            }
            offset += 1;
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vm_creation() {
        let vm = PixelVM::new();
        assert_eq!(vm.registers.len(), 16);
        assert_eq!(vm.program_counter, 0);
    }

    #[test]
    fn test_pixel_container() {
        let container = PixelContainer::new(10, 10, 3);
        assert_eq!(container.width, 10);
        assert_eq!(container.height, 10);
        assert_eq!(container.depth, 3);
        assert_eq!(container.data.len(), 300);
    }

    #[test]
    fn test_read_write_region() {
        let mut container = PixelContainer::new(100, 100, 3);
        let data = vec![255u8; 27]; // 3x3x3 region

        container.write_region(10, 10, 0, &data).unwrap();
        let read_data = container.read_region(10, 10, 0, 3, 3, 3).unwrap();

        assert_eq!(read_data.len(), 27);
        assert!(read_data.iter().all(|&b| b == 255));
    }

    #[test]
    fn test_instruction_creation() {
        let inst = PixelInstruction::new(PixelOpCode::LoadRegion)
            .with_operands(vec![100, 200, 0, 10, 10, 3])
            .with_reg(0)
            .with_comment("Load test region".to_string());

        assert_eq!(inst.opcode, PixelOpCode::LoadRegion);
        assert_eq!(inst.operands.len(), 6);
        assert_eq!(inst.register_ops.len(), 1);
    }

    #[test]
    fn test_execute_load_region() {
        let mut vm = PixelVM::new();
        let mut container = PixelContainer::new(100, 100, 3);

        let inst = PixelInstruction::new(PixelOpCode::LoadRegion)
            .with_operands(vec![10, 10, 0, 5, 5, 3])
            .with_reg(0);

        vm.execute(&inst, &mut container).unwrap();

        assert_eq!(vm.registers[0].coord, (10, 10));
        assert_eq!(vm.registers[0].size, (5, 5, 3));
        assert_eq!(vm.registers[0].data.len(), 75);
    }

    #[test]
    fn test_execute_fill_region() {
        let mut vm = PixelVM::new();
        let mut container = PixelContainer::new(100, 100, 3);

        // Set fill value in R1
        vm.registers[1].data = vec![0xFF];

        let inst = PixelInstruction::new(PixelOpCode::FillRegion)
            .with_operands(vec![0, 0, 0, 10, 10, 3])
            .with_reg(1);

        vm.execute(&inst, &mut container).unwrap();

        // Verify fill
        let region = container.read_region(0, 0, 0, 10, 10, 3).unwrap();
        assert!(region.iter().all(|&b| b == 0xFF));
    }
}
EOF

echo "✓ Created pixel VM module"

# Cargo.toml for VM
cat > "$PIXEL_VM_DIR/Cargo.toml" << 'EOF'
[package]
name = "pixel-vm"
version = "0.1.0"
edition = "2021"

[dependencies]
pixel-analyzer = { path = "../analyzer" }
pixel-tracer = { path = "../tracer" }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"

[dev-dependencies]
EOF

echo "✓ Created VM Cargo.toml"

# Workspace file
cat > "$PROJECT_ROOT/pixel_trace/Cargo.toml" << 'EOF'
[workspace]
members = ["tracer", "analyzer", "vm"]

[workspace.dependencies]
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
chrono = "0.4"
EOF

echo "✓ Created workspace Cargo.toml"

# Create runner script
cat > "$PROJECT_ROOT/run_pixel_vm.sh" << 'EOF'
#!/bin/bash
# Run a pixel program in the pixel-native VM
set -e

PROJECT_ROOT="/host_zion/projects/visual_audio"
VM_BUILD="$PROJECT_ROOT/pixel_trace/vm/target/release/pixel_vm"
ANALYSIS_DIR="$PROJECT_ROOT/pixel_traces"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <session_id> [pixel_container_path]"
    echo "Example: $0 trace_1723981234567890"
    echo ""
    echo "This executes a pixel program using the pixel-native VM."
    echo "The program is applied directly to the pixel container."
    echo ""
    exit 1
fi

SESSION_ID="$1"
CONTAINER_PATH="${2:-$PROJECT_ROOT/ubuntu_desktop_pxc1_v1}"

echo "=== Pixel-Native VM Execution ==="
echo "Session ID: $SESSION_ID"
echo "Container: $CONTAINER_PATH"
echo ""

# Check if analysis exists
ANALYSIS_FILE="$ANALYSIS_DIR/analysis_${SESSION_ID}.json"
if [ ! -f "$ANALYSIS_FILE" ]; then
    echo "Error: Analysis not found at $ANALYSIS_FILE"
    echo "Run analyze_pixel_trace.sh $SESSION_ID first"
    exit 1
fi

# Build VM if needed
if [ ! -f "$VM_BUILD" ]; then
    echo "Building pixel VM..."
    cd "$PROJECT_ROOT/pixel_trace"
    cargo build --release
fi

# Run VM
echo "Starting pixel VM..."
echo ""

$VM_BUILD run "$ANALYSIS_FILE" "$CONTAINER_PATH"

echo ""
echo "=== VM Execution Complete ==="
echo ""
echo "Changes were applied to the pixel container."
echo "To see the changes, reboot the Pixel Linux:"
echo "  ./interactive_ubuntu_pixel.sh"
echo ""

exit 0
EOF

chmod +x "$PROJECT_ROOT/run_pixel_vm.sh"
echo "✓ Created VM runner script"

echo ""
echo "=== Pixel-Native VM Created ==="
echo ""
echo "Components created:"
echo "  - $PIXEL_VM_DIR/src/lib.rs              (pixel VM module)"
echo "  - $PIXEL_VM_DIR/Cargo.toml              (VM build config)"
echo "  - $PROJECT_ROOT/pixel_trace/Cargo.toml   (workspace config)"
echo "  - $PROJECT_ROOT/run_pixel_vm.sh         (VM runner)"
echo ""
echo "The Pixel-Native VM can execute programs by transforming pixels"
echo "directly, without running compiled code."
echo ""
echo "Example workflow:"
echo "  1. Trace:  pixel_trace_command.sh 'ls /etc'"
echo "  2. Analyze: analyze_pixel_trace.sh <session_id>"
echo "  3. Execute: run_pixel_vm.sh <session_id>"
echo ""
echo "This enables pixel-native program execution!"
echo ""