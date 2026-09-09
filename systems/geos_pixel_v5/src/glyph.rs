//! Phase 5: Rust glyph interpreter — executes `.glyph` assembly directly
//! against WCB `data_memory`.
//!
//! Phase 4 proved the self-hosting *load* path: a `.glyph` program and its
//! window manifest are decoded from the PDB and placed into spatial memory.
//! Phase 5 completes the loop by *executing* that program: a small
//! interpreter with semantics mirroring the Python reference
//! (`tools/glyph_isa_v2.py` `GlyphCPUv2`) runs the spatial coordinator
//! supervisor loop, which CALLR-dispatches each active window's tick routine
//! and mutates its WCB row (X/Y drift, tick counters) — the same
//! `data_memory` words the GPU render shader composites.
//!
//! ## ISA (subset implemented; superset of what spatial_coordinator.glyph uses)
//!
//! | opcode | semantics (mirrors GlyphCPUv2)                       |
//! |--------|------------------------------------------------------|
//! | LDI rd imm | rd = imm                                       |
//! | ADD/SUB/AND/OR/XOR/SHL/SHR rd rs | rd op= regs[rs] |
//! | CMP rd rs | r0 = (regs[rd] == regs[rs]) ? 1 : 0           |
//! | LD rd rs | rd = mem[regs[rs]] (data_memory words)          |
//! | ST addr_reg val_reg | mem[regs[addr_reg]] = regs[val_reg] |
//! | JMP/JZ/CALL :label | control flow to resolved linear index   |
//! | CALLR rX | push packed(next_pc); pc = unpack(regs[rX])     |
//! | JMPR rX | pc = unpack(regs[rX])                            |
//! | RET | pc = unpack(pop)                                   |
//! | PUSH/POP rX | r31-descending stack in program space      |
//! | PRT rX | record regs[rX] in output                          |
//! | HALT | stop                                               |
//!
//! Packed addresses use the reference encoding `(row<<16)|col` where `col`
//! is the *instruction column* (0..width_instrs). The Python `CALLR` expects
//! exactly this packing in the TICK_ADDR word, so WCB rows seeded with a
//! tick routine's packed address are portable between executors.
//!
//! ## Memory model
//!
//! `LD`/`ST` access the `data_memory` i32 buffer passed to `step`/`run` —
//! the same buffer `WindowSystem` uploads to the GPU. The supervisor sets
//! r3 = WCB_BASE (100) and r4 = current WCB row, so tick routines read/write
//! their own 64-byte row r4-relative (offset 1 = X, 2 = Y, 7 = counter),
//! exactly as `spatial_coordinator.glyph` documents.

use std::collections::HashMap;

/// Stack base for CALL/CALLR/RET and PUSH/POP (mirrors `LDI r31 250`).
pub const STACK_BASE: i32 = 250;
/// Maximum steps a single `run()` will execute before returning (safety).
pub const MAX_STEPS: usize = 1_000_000;

/// Glyph opcodes (superset of the coordinator's needs).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Opcode {
    Halt,
    Ldi,
    Add,
    Sub,
    And,
    Or,
    Xor,
    Shl,
    Shr,
    Cmp,
    Ld,
    St,
    Prt,
    Push,
    Pop,
    Call,
    Ret,
    Jmpr,
    Callr,
    Jmp,
    Jz,
}

/// A decoded instruction (labels already resolved to linear indices).
#[derive(Debug, Clone)]
pub struct Instruction {
    pub opcode: Opcode,
    pub rd: u8,
    pub rs1: u8,
    pub rs2: u8,
    pub imm: i32,
    /// Linear instruction index target for JMP/JZ/CALL (resolved label).
    pub target: usize,
}

/// Parsed + assembled glyph program.
#[derive(Debug, Clone)]
pub struct GlyphProgram {
    pub instrs: Vec<Instruction>,
    /// label name -> linear instruction index.
    pub labels: HashMap<String, usize>,
    /// instructions per row (row-major layout used for packed addresses).
    pub width_instrs: usize,
}

impl GlyphProgram {
    /// Assemble `.glyph` source text into a program.
    ///
    /// Accepts the dialect used by `spatial_coordinator.glyph`: `#` comments,
    /// `:label` definitions, `rN` registers, decimal/hex immediates, and
    /// label targets for JMP/JZ/CALL. `width_instrs` controls the row-major
    /// layout for packed addresses (reference uses 8).
    pub fn assemble(source: &str, width_instrs: usize) -> Result<Self, String> {
        if width_instrs == 0 {
            return Err("width_instrs must be > 0".into());
        }

        // Pass 1: strip comments/blank lines, collect labels + raw instructions.
        #[derive(Clone)]
        struct Raw {
            opcode: Opcode,
            rd: u8,
            rs1: u8,
            rs2: u8,
            imm: i32,
            label: Option<String>,
        }

        let mut raws: Vec<Raw> = Vec::new();
        let mut labels: HashMap<String, usize> = HashMap::new();

        for (lineno, raw_line) in source.lines().enumerate() {
            // Strip both '#' (file header) and ';' (inline) comments — the
            // .glyph dialect uses both.
            let line = raw_line
                .split(['#', ';'])
                .next()
                .unwrap_or("")
                .trim();
            if line.is_empty() {
                continue;
            }
            if let Some(name) = line.strip_prefix(':') {
                let name = name.trim().to_string();
                if labels.insert(name.clone(), raws.len()).is_some() {
                    return Err(format!("line {}: duplicate label '{}'", lineno + 1, name));
                }
                continue;
            }
            let parts: Vec<&str> = line.split_whitespace().collect();
            let opcode = parse_opcode(parts[0])
                .ok_or_else(|| format!("line {}: unknown opcode '{}'", lineno + 1, parts[0]))?;
            let args = &parts[1..];

            let mut r = Raw {
                opcode,
                rd: 0,
                rs1: 0,
                rs2: 0,
                imm: 0,
                label: None,
            };

            macro_rules! reg {
                ($a:expr, $what:expr) => {{
                    parse_register($a).ok_or_else(|| {
                        format!("line {}: bad register '{}' for {}", lineno + 1, $a, $what)
                    })?
                }};
            }
            macro_rules! imm {
                ($a:expr, $what:expr) => {{
                    parse_immediate($a).ok_or_else(|| {
                        format!("line {}: bad immediate '{}' for {}", lineno + 1, $a, $what)
                    })?
                }};
            }

            match opcode {
                Opcode::Ldi => {
                    if args.len() != 2 {
                        return Err(format!("line {}: LDI needs rd imm", lineno + 1));
                    }
                    r.rd = reg!(args[0], "LDI");
                    r.imm = imm!(args[1], "LDI");
                }
                Opcode::Add | Opcode::Sub | Opcode::And | Opcode::Or | Opcode::Xor
                | Opcode::Shl | Opcode::Shr | Opcode::Cmp | Opcode::Ld => {
                    if args.len() != 2 {
                        return Err(format!("line {}: {} needs rd rs", lineno + 1, parts[0]));
                    }
                    r.rd = reg!(args[0], parts[0]);
                    r.rs2 = reg!(args[1], parts[0]);
                }
                Opcode::St => {
                    if args.len() != 2 {
                        return Err(format!("line {}: ST needs addr_reg val_reg", lineno + 1));
                    }
                    r.rs1 = reg!(args[0], "ST");
                    r.rs2 = reg!(args[1], "ST");
                }
                Opcode::Jmp | Opcode::Jz | Opcode::Call => {
                    if args.len() != 1 {
                        return Err(format!("line {}: {} needs :label", lineno + 1, parts[0]));
                    }
                    let t = args[0].trim_start_matches(':').to_string();
                    r.label = Some(t);
                }
                Opcode::Jmpr | Opcode::Callr | Opcode::Push | Opcode::Pop | Opcode::Prt => {
                    if args.len() != 1 {
                        return Err(format!("line {}: {} needs rX", lineno + 1, parts[0]));
                    }
                    r.rd = reg!(args[0], parts[0]);
                }
                Opcode::Halt | Opcode::Ret => {
                    if !args.is_empty() {
                        return Err(format!("line {}: {} takes no operands", lineno + 1, parts[0]));
                    }
                }
            }

            raws.push(r);
        }

        // Pass 2: resolve label targets into linear indices.
        let mut instrs = Vec::with_capacity(raws.len());
        for (i, raw) in raws.iter().enumerate() {
            let target = match &raw.label {
                Some(name) => *labels
                    .get(name)
                    .ok_or_else(|| format!("instruction {}: unknown label '{}'", i, name))?,
                None => 0,
            };
            instrs.push(Instruction {
                opcode: raw.opcode,
                rd: raw.rd,
                rs1: raw.rs1,
                rs2: raw.rs2,
                imm: raw.imm,
                target,
            });
        }

        Ok(Self {
            instrs,
            labels,
            width_instrs,
        })
    }

    /// Pack a linear instruction index into the reference `(row<<16)|col`
    /// address (col in instruction units). Used to seed WCB TICK_ADDR.
    pub fn packed_addr(&self, index: usize) -> u32 {
        packed_addr(index, self.width_instrs)
    }

    /// Unpack a packed address to a linear instruction index.
    pub fn unpack_addr(&self, packed: u32) -> usize {
        unpack_addr(packed, self.width_instrs)
    }

    /// Look up a label's packed address.
    pub fn label_packed(&self, name: &str) -> Option<u32> {
        self.labels.get(name).map(|&i| self.packed_addr(i))
    }
}

/// Pack `(row<<16)|col`, col in instruction units.
pub fn packed_addr(index: usize, width_instrs: usize) -> u32 {
    let row = (index / width_instrs) as u32;
    let col = (index % width_instrs) as u32;
    (row << 16) | col
}

/// Unpack `(row<<16)|col` to a linear instruction index.
pub fn unpack_addr(packed: u32, width_instrs: usize) -> usize {
    let col = (packed & 0xFFFF) as usize;
    let row = (packed >> 16) as usize;
    row * width_instrs + col
}

/// The interpreter: registers + program-space stack; memory is borrowed per
/// `step`/`run` call so the same CPU can drive different buffers.
#[derive(Debug)]
pub struct GlyphCpu {
    pub regs: [i32; 32],
    pub pc: usize,
    pub running: bool,
    pub output: Vec<i32>,
    stack: Vec<i32>,
}

impl Default for GlyphCpu {
    fn default() -> Self {
        Self::new()
    }
}

impl GlyphCpu {
    pub fn new() -> Self {
        let mut regs = [0i32; 32];
        regs[31] = STACK_BASE;
        Self {
            regs,
            pc: 0,
            running: true,
            output: Vec::new(),
            stack: Vec::new(),
        }
    }

    /// Execute one instruction against `mem` (WCB `data_memory` words).
    /// Returns false when the program halts or runs off the end.
    pub fn step(&mut self, prog: &GlyphProgram, mem: &mut [i32]) -> bool {
        if !self.running {
            return false;
        }
        if self.pc >= prog.instrs.len() {
            self.running = false;
            return false;
        }
        let insn = &prog.instrs[self.pc];
        let next = self.pc + 1;

        match insn.opcode {
            Opcode::Halt => {
                self.running = false;
                return false;
            }
            Opcode::Ldi => self.regs[insn.rd as usize] = insn.imm,
            Opcode::Add => {
                let (rd, rs) = (insn.rd as usize, insn.rs2 as usize);
                self.regs[rd] = self.regs[rd].wrapping_add(self.regs[rs]);
            }
            Opcode::Sub => {
                let (rd, rs) = (insn.rd as usize, insn.rs2 as usize);
                self.regs[rd] = self.regs[rd].wrapping_sub(self.regs[rs]);
            }
            Opcode::And => {
                let (rd, rs) = (insn.rd as usize, insn.rs2 as usize);
                self.regs[rd] &= self.regs[rs];
            }
            Opcode::Or => {
                let (rd, rs) = (insn.rd as usize, insn.rs2 as usize);
                self.regs[rd] |= self.regs[rs];
            }
            Opcode::Xor => {
                let (rd, rs) = (insn.rd as usize, insn.rs2 as usize);
                self.regs[rd] ^= self.regs[rs];
            }
            Opcode::Shl => {
                let (rd, rs) = (insn.rd as usize, insn.rs2 as usize);
                self.regs[rd] = self.regs[rd].wrapping_shl(self.regs[rs] as u32);
            }
            Opcode::Shr => {
                let (rd, rs) = (insn.rd as usize, insn.rs2 as usize);
                self.regs[rd] = (self.regs[rd] as u32).wrapping_shr(self.regs[rs] as u32) as i32;
            }
            Opcode::Cmp => {
                let (rd, rs) = (insn.rd as usize, insn.rs2 as usize);
                self.regs[0] = if self.regs[rd] == self.regs[rs] { 1 } else { 0 };
            }
            Opcode::Ld => {
                let addr = self.regs[insn.rs2 as usize] as usize;
                if addr < mem.len() {
                    self.regs[insn.rd as usize] = mem[addr];
                }
            }
            Opcode::St => {
                let addr = self.regs[insn.rs1 as usize] as usize;
                if addr < mem.len() {
                    mem[addr] = self.regs[insn.rs2 as usize];
                }
            }
            Opcode::Prt => self.output.push(self.regs[insn.rd as usize]),
            Opcode::Push => {
                self.regs[31] -= 1;
                self.stack.push(self.regs[insn.rd as usize]);
            }
            Opcode::Pop => {
                if let Some(v) = self.stack.pop() {
                    self.regs[insn.rd as usize] = v;
                    self.regs[31] += 1;
                }
            }
            Opcode::Call => {
                self.regs[31] -= 1;
                self.stack
                    .push(prog.packed_addr(next) as i32);
                self.pc = insn.target;
                return true;
            }
            Opcode::Ret => {
                if let Some(packed) = self.stack.pop() {
                    self.regs[31] += 1;
                    self.pc = prog.unpack_addr(packed as u32);
                    return true;
                }
                // RET with empty stack: stop (protects the supervisor loop
                // from runaway dispatches if a tick routine returns twice).
                self.running = false;
                return false;
            }
            Opcode::Jmpr => {
                self.pc = prog.unpack_addr(self.regs[insn.rd as usize] as u32);
                return true;
            }
            Opcode::Callr => {
                self.regs[31] -= 1;
                self.stack
                    .push(prog.packed_addr(next) as i32);
                self.pc = prog.unpack_addr(self.regs[insn.rd as usize] as u32);
                return true;
            }
            Opcode::Jmp => {
                self.pc = insn.target;
                return true;
            }
            Opcode::Jz => {
                if self.regs[0] != 0 {
                    self.pc = insn.target;
                    return true;
                }
            }
        }

        self.pc = next;
        true
    }

    /// Run until HALT, program end, or `max_steps`. Returns steps executed.
    pub fn run(&mut self, prog: &GlyphProgram, mem: &mut [i32], max_steps: usize) -> usize {
        let mut n = 0;
        while n < max_steps {
            if !self.step(prog, mem) {
                break;
            }
            n += 1;
        }
        n
    }
}

fn parse_opcode(s: &str) -> Option<Opcode> {
    Some(match s.to_ascii_uppercase().as_str() {
        "HALT" => Opcode::Halt,
        "LDI" => Opcode::Ldi,
        "ADD" => Opcode::Add,
        "SUB" => Opcode::Sub,
        "AND" => Opcode::And,
        "OR" => Opcode::Or,
        "XOR" => Opcode::Xor,
        "SHL" => Opcode::Shl,
        "SHR" => Opcode::Shr,
        "CMP" => Opcode::Cmp,
        "LD" => Opcode::Ld,
        "ST" => Opcode::St,
        "PRT" => Opcode::Prt,
        "PUSH" => Opcode::Push,
        "POP" => Opcode::Pop,
        "CALL" => Opcode::Call,
        "RET" => Opcode::Ret,
        "JMPR" => Opcode::Jmpr,
        "CALLR" => Opcode::Callr,
        "JMP" => Opcode::Jmp,
        "JZ" => Opcode::Jz,
        _ => return None,
    })
}

fn parse_register(s: &str) -> Option<u8> {
    let n = s.strip_prefix('r').or_else(|| s.strip_prefix('R'))?;
    let v: u8 = n.parse().ok()?;
    (v < 32).then_some(v)
}

fn parse_immediate(s: &str) -> Option<i32> {
    if let Some(hex) = s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")) {
        i32::from_str_radix(hex, 16).ok()
    } else {
        s.parse::<i32>().ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::wcb::{seed_wcb_state, MEM_WORDS};

    fn mem() -> Vec<i32> {
        vec![0i32; MEM_WORDS]
    }

    #[test]
    fn test_parse_register_and_immediate() {
        assert_eq!(parse_register("r31"), Some(31));
        assert_eq!(parse_register("r0"), Some(0));
        assert_eq!(parse_register("r32"), None);
        assert_eq!(parse_register("x5"), None);
        assert_eq!(parse_immediate("250"), Some(250));
        assert_eq!(parse_immediate("0x10"), Some(16));
        assert_eq!(parse_immediate("0XFF"), Some(255));
        assert_eq!(parse_immediate("abc"), None);
    }

    #[test]
    fn test_packed_addr_roundtrip() {
        for idx in 0..64 {
            let packed = packed_addr(idx, 8);
            assert_eq!(unpack_addr(packed, 8), idx);
        }
        // Known layout: index 26 -> row 3, col 2.
        assert_eq!(packed_addr(26, 8), (3 << 16) | 2);
    }

    #[test]
    fn test_assemble_labels() {
        let src = "\
# comment
:start
LDI r1 5
CMP r1 r2
JZ :done
JMP :start
:done
HALT
";
        let prog = GlyphProgram::assemble(src, 8).unwrap();
        assert_eq!(prog.instrs.len(), 5);
        assert_eq!(*prog.labels.get("start").unwrap(), 0);
        assert_eq!(*prog.labels.get("done").unwrap(), 4);
        // JZ target resolved to index 4.
        assert_eq!(prog.instrs[2].opcode, Opcode::Jz);
        assert_eq!(prog.instrs[2].target, 4);
        assert_eq!(prog.instrs[3].target, 0);
    }

    #[test]
    fn test_assemble_errors() {
        assert!(GlyphProgram::assemble("BOGUS r1 5\n", 8).is_err());
        assert!(GlyphProgram::assemble("LDI r1\n", 8).is_err());
        assert!(GlyphProgram::assemble("LDI r1 5\nJZ :missing\n", 8).is_err());
        assert!(GlyphProgram::assemble(":a\nLDI r1 1\n:a\n", 8).is_err());
    }

    #[test]
    fn test_counting_loop_matches_python_demo() {
        // Mirror of tools/glyph_isa_v2.py demo(): count 0..4 then halt.
        let src = "\
LDI r5 0
LDI r1 5
:loop
CMP r5 r1
JZ :done
PRT r5
LDI r2 1
ADD r5 r2
JMP :loop
:done
HALT
";
        let prog = GlyphProgram::assemble(src, 8).unwrap();
        let mut cpu = GlyphCpu::new();
        let mut m = mem();
        let n = cpu.run(&prog, &mut m, 1000);
        assert!(n > 0);
        assert_eq!(cpu.output, vec![0, 1, 2, 3, 4]);
        assert_eq!(cpu.regs[5], 5);
    }

    #[test]
    fn test_ld_st_word_memory() {
        let src = "\
LDI r1 100
LDI r2 42
ST r1 r2
LDI r3 100
LD r4 r3
HALT
";
        let prog = GlyphProgram::assemble(src, 8).unwrap();
        let mut cpu = GlyphCpu::new();
        let mut m = mem();
        cpu.run(&prog, &mut m, 100);
        assert_eq!(m[100], 42, "ST wrote 42 to word 100");
        assert_eq!(cpu.regs[4], 42, "LD read it back into r4");
    }

    #[test]
    fn test_call_ret_roundtrip() {
        let src = "\
:main
LDI r1 7
CALL :sub
LDI r2 99
HALT
:sub
LDI r3 1
ADD r3 r1
RET
";
        let prog = GlyphProgram::assemble(src, 8).unwrap();
        let mut cpu = GlyphCpu::new();
        let mut m = mem();
        cpu.run(&prog, &mut m, 100);
        assert_eq!(cpu.regs[1], 7);
        assert_eq!(cpu.regs[2], 99, "execution resumed after CALL/RET");
        assert_eq!(cpu.regs[3], 8, "subroutine computed 7+1");
        assert_eq!(cpu.regs[31], STACK_BASE, "stack pointer balanced");
    }

    #[test]
    fn test_callr_ret_dynamic_dispatch() {
        // CALLR to a packed address held in a register (like the supervisor
        // loading TICK_ADDR from a WCB row). The target is resolved from the
        // assembled program's label table — data-driven dispatch.
        let src = "\
:main
LDI r1 100
LD r8 r1
CALLR r8
LDI r3 77
HALT
:tick
LDI r4 5
ADD r4 r4
RET
";
        let prog = GlyphProgram::assemble(src, 8).unwrap();
        let packed = prog.label_packed("tick").unwrap();
        let mut cpu = GlyphCpu::new();
        let mut m = mem();
        m[100] = packed as i32; // WCB-style TICK_ADDR slot
        cpu.run(&prog, &mut m, 100);
        assert_eq!(cpu.regs[3], 77, "resumed after CALLR/RET");
        assert_eq!(cpu.regs[4], 10, "tick routine ran (5+5)");
        assert_eq!(cpu.regs[31], STACK_BASE, "stack balanced");
    }

    #[test]
    fn test_supervisor_dispatch_on_wcb() {
        // The canonical spatial_coordinator.glyph from the repo root.
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../spatial_coordinator.glyph");
        let src = std::fs::read_to_string(path).expect("spatial_coordinator.glyph readable");
        let prog = GlyphProgram::assemble(&src, 8).unwrap();

        // Supervisor loop is infinite; run a bounded number of passes.
        let mut cpu = GlyphCpu::new();
        let mut m = mem();
        seed_wcb_state(&mut m);
        // Seed TICK_ADDR for active windows to their real tick routines
        // (Phase 5 manifest semantics).
        for (tick_label, i) in [
            ("window_tick0", 0usize),
            ("window_tick1", 1),
            ("window_tick2", 2),
        ] {
            let packed = prog.label_packed(tick_label).expect("tick label exists");
            let base = crate::wcb::WCB_BASE + i * crate::wcb::WCB_STRIDE;
            m[base + 6] = packed as i32;
        }

        // 3 active windows; give the loop enough budget for several full
        // passes (the supervisor never halts — it's an infinite loop).
        let steps = cpu.run(&prog, &mut m, 5000);
        assert!(steps >= 5000, "supervisor loop ran to budget, got {steps}");
        assert!(steps > 0);

        // window_tick0 increments X (offset 1) and counter (offset 7);
        // window_tick2 increments Y (offset 2) and counter; tick1 counter only.
        let b0 = crate::wcb::WCB_BASE;
        let b1 = crate::wcb::WCB_BASE + crate::wcb::WCB_STRIDE;
        let b2 = crate::wcb::WCB_BASE + 2 * crate::wcb::WCB_STRIDE;
        // At least one full pass completed for all three active windows.
        assert!(m[b0 + 7] >= 1, "WCB0 counter incremented");
        assert!(m[b1 + 7] >= 1, "WCB1 counter incremented");
        assert!(m[b2 + 7] >= 1, "WCB2 counter incremented");
        // Each pass dispatches every active window once, so counters can
        // differ by at most 1 (a bounded run may stop mid-pass; tick0/tick2
        // cost more instructions than tick1).
        assert!((m[b0 + 7] - m[b1 + 7]).abs() <= 1, "WCB0/WCB1 counters in lockstep");
        assert!((m[b0 + 7] - m[b2 + 7]).abs() <= 1, "WCB0/WCB2 counters in lockstep");
        // X drifted right, Y drifted down.
        assert_eq!(m[b0 + 1], 50 + m[b0 + 7], "WCB0 X drifts +1 per pass");
        assert_eq!(m[b2 + 2], 20 + m[b2 + 7], "WCB2 Y drifts +1 per pass");
        // WCB1 X unchanged (tick1 doesn't touch it).
        assert_eq!(m[b1 + 1], 100, "WCB1 X untouched");
    }
}
