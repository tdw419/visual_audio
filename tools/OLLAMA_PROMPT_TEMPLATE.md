# Ollama-Driven Development Prompt Template

Copy and paste this prompt when you want me to use the Ollama analyzer suite and skeleton-driven development workflow.

---

## Prompt to Use

```
[OLLAMA-DRIVEN DEVELOPMENT TASK]

I want you to build [WHAT] using the Ollama analyzer suite and skeleton-driven development workflow.

Context:
- Project: Visual Audio — spatial compute OS + audio codec system
- Agent Constitution rules: VCC compliance, formant-informed envelopes, 20ms symbol duration, CMUdict caching
- Performance target: [specify if applicable]
- Verification gates: codec roundtrip, dual-band encoding, VCC compliance tests

Task:
[Describe what needs to be built - e.g., "a GPU-native RISC-V emulator", "error correction layer for codec", etc.]

Requirements:
[Specific requirements - e.g., "must handle add, sub, and, or, xor instructions", "must achieve 4-6x speedup over QEMU", etc.]

Use this workflow:

1. Generate skeleton using appropriate template (generic/codec/tool/test/spatial)
2. Implement core functionality
3. Run Ollama analysis iteratively:
   - First pass: architecture (get structure right)
   - Fix HIGH findings
   - Second pass: performance (if performance-critical)
   - Fix HIGH findings
   - Final pass: security, style, testing (as needed)
4. Run tests and verification gates
5. Mark ROADMAP task complete

Documentation:
- Save review documents for each analysis pass
- Document any tradeoffs for MEDIUM/LOW findings
- Update AGENTS.md if rules change

Priority:
- HIGH findings: must fix before proceeding
- MEDIUM findings: fix if time permits, document tradeoffs
- LOW findings: optional, defer if needed

Stop and ask me:
- Only if you genuinely have zero signal on product direction
- If you need explicit user approval for external actions (emails, tweets, etc.)
- Never ask for implementation choices — make the decision and proceed
```

---

## Example Prompts

### Example 1: Spatial CPU Development

```
[OLLAMA-DRIVEN DEVELOPMENT TASK]

I want you to build a GPU-native RISC-V emulator using the Ollama analyzer suite and skeleton-driven development workflow.

Context:
- Project: Visual Audio — spatial compute OS + audio codec system
- Agent Constitution rules: VCC compliance, preserve Hilbert curve mapping in spatial transformations
- Performance target: 4-6x speedup over QEMU-based GPU emulator
- Verification gates: VCC compliance tests, performance benchmarks

Task:
Build a spatial RISC-V core that executes RISC-V RV32I binaries on GPU without CPU-side emulation.

Requirements:
- Support basic RV32I instructions: addi, add, and, or, xor, lw, sw, jal, beq
- GPU-native execution (dispatch work to WGSL compute shader)
- Pixel-grid aligned memory (Hilbert curve mapping preserved)
- Register file, ALU, and instruction decode all execute on GPU
- No CPU-side instruction emulation

Use this workflow:

1. Generate skeleton using "spatial" template
2. Implement core functionality:
   - RegisterFile class (32 × 32-bit GPU memory)
   - MemoryRegion class (GPU-resident, Hilbert-ordered)
   - Fetch, decode, execute pipeline
   - Basic instruction implementations (addi, add, and, or, xor)
3. Run Ollama analysis iteratively:
   - First pass: architecture (VCC compliance, spatial invariant)
   - Fix HIGH findings
   - Second pass: performance (GPU dispatch, memory allocation)
   - Fix HIGH findings
   - Final pass: security, style, testing
4. Run tests and verification gates:
   - pytest tests/test_spatial_cpu.py
   - python3 -m pytest tests/test_vcc.py
   - python3 tests/benchmark_spatial_cpu.py (verify 4-6x speedup)
5. Mark ROADMAP task complete

Documentation:
- Save review documents: spatial_cpu_arch.md, spatial_cpu_perf.md, spatial_cpu_final.md
- Document any tradeoffs for MEDIUM/LOW findings

Priority:
- HIGH findings: must fix before proceeding
- MEDIUM findings: fix if time permits, document tradeoffs
- LOW findings: optional, defer if needed

Stop and ask me:
- Only if you genuinely have zero signal on product direction
- Never ask for implementation choices — make the decision and proceed
```

### Example 2: Error Correction Layer

```
[OLLAMA-DRIVEN DEVELOPMENT TASK]

I want you to build an error correction layer for the Visual Audio codec using the Ollama analyzer suite and skeleton-driven development workflow.

Context:
- Project: Visual Audio — three-layer encoding system (phoneme, byte, dual-band)
- Agent Constitution rules: 20ms phoneme duration (don't change without VCC validation), CMUdict caching
- Performance target: maintain current throughput (~7.6 words/sec phoneme, ~24 bytes/sec byte)
- Verification gates: codec roundtrip (encode → decode → bit-identical)

Task:
Add Reed-Solomon error correction layer to protect against transmission errors.

Requirements:
- Protect phoneme sequences (39 ARPAbet templates)
- Protect byte layer (16-tone MFSK encoding)
- Add configurable redundancy (e.g., recover from N% symbol loss)
- No performance regression in error-free case
- Bit-perfect roundtrip in error-free case

Use this workflow:

1. Generate skeleton using "codec" template
2. Implement core functionality:
   - ReedSolomonLayer class with encode() and decode() methods
   - Parity generation using reedsolo library
   - Error detection and correction
   - Test harness for error injection
3. Run Ollama analysis iteratively:
   - First pass: architecture (layer integration with phoneme/byte layers)
   - Fix HIGH findings
   - Second pass: performance (no regression in error-free case)
   - Fix HIGH findings
   - Final pass: security (handle malformed input), style, testing
4. Run tests and verification gates:
   - pytest tests/test_ecc_layer.py
   - Codec roundtrip with ECC enabled (encode → decode → bit-identical)
   - Error recovery tests (inject errors, verify correction)
   - Performance tests (no regression vs baseline)
5. Mark ROADMAP task complete

Documentation:
- Save review documents: ecc_arch.md, ecc_perf.md, ecc_final.md
- Document error recovery capabilities and tradeoffs

Priority:
- HIGH findings: must fix before proceeding
- MEDIUM findings: fix if time permits, document tradeoffs
- LOW findings: optional, defer if needed

Stop and ask me:
- Only if you genuinely have zero signal on product direction
- Never ask for implementation choices — make the decision and proceed
```

### Example 3: Quick Bug Fix

```
[OLLAMA-DRIVEN DEVELOPMENT TASK - QUICK FIX]

I want you to fix a bug in the spatial RISC-V core using the Ollama analyzer suite (single-pass only).

Context:
- Project: Visual Audio — spatial compute OS
- Bug: add instruction works incorrectly (x2 should be 10 but gets 0)
- Test: test_addi_add() in tests/test_spatial_cpu.py

Task:
Debug and fix the add instruction execution bug.

Requirements:
- Add instruction: add x2, x1, x1 should produce x2 = x1 + x1
- addi instruction already works correctly (x1 = 5)
- No performance regression expected

Use this workflow:

1. Quick debug:
   - Reproduce bug: python3 tests/test_spatial_cpu.py
   - Analyze instruction encoding: manual decode check
   - Identify root cause (likely in execute() or decode())
2. Fix the bug
3. Run single analysis pass (architecture only):
   - python3 tools/ollama_analyzer.py --files src/spatial_cpu/*.py --review bugfix_review.md --passes architecture
4. Apply HIGH findings if any
5. Run tests:
   - pytest tests/test_spatial_cpu.py
6. Mark fix complete

Documentation:
- Save review document: bugfix_review.md

Priority:
- HIGH findings: must fix before proceeding
- MEDIUM/LOW findings: skip (this is a quick fix)

Stop and ask me:
- Only if you genuinely have zero signal
- Never ask for implementation choices — make the decision and proceed
```

### Example 4: Incremental Diff Analysis (Skeleton Lock)

```
[OLLAMA-DRIVEN DEVELOPMENT TASK - SKELETON REVIEW]

I want you to use the Incremental Ollama Analysis workflow to lock in a skeleton revision.

Context:
- Project: Visual Audio
- Goal: Lock down the architectural boundaries before filling implementation.

Task:
Perform an iterative diff review on the latest skeleton changes.

Use this workflow:
1. Commit the latest skeleton changes.
2. Generate the diff: `git diff HEAD~1 > /tmp/rev.diff`
3. Feed the diff to Ollama using the CLI Prompt Template below.
4. Append the results to ANALYSIS.md.
5. Review the findings, apply changes, and repeat until the architecture is locked.
```

---

## Ollama CLI Diff Analysis Prompt

When executing Phase 2 of the **Incremental Ollama Analysis** workflow, use the following system prompt to feed the diff directly to the local model via the CLI.

```bash
# 1. Generate diff
git diff HEAD~1 > /tmp/rev.diff

# 2. Run analysis (Adjust model tag as needed)
ollama run qwen2.5-coder:14b "You are an expert systems architect reviewing a code diff for a project utilizing a Skeleton-Driven Development workflow. 

Your objective is NOT to rewrite the code, but to provide a strict architectural review of the provided diff. Keep in mind that many function bodies may intentionally be empty stubs at this phase.

Please analyze the provided diff and return your findings in the following strictly formatted markdown sections:

### Ollama Findings:
**Suggestions:**
- [Provide concise, actionable suggestions regarding structural integrity or design patterns]

**Risks Identified:**
- [Identify any type safety issues, boundary inconsistencies, memory leaks, or logical gaps introduced in the diff]

**Architectural Notes:**
- [Highlight deviations from expected contracts, missing required side effects, or cross-boundary communication issues]" < /tmp/rev.diff >> ANALYSIS.md
```

---

## Blank Template (Fill in the Brackets)

```
[OLLAMA-DRIVEN DEVELOPMENT TASK]

I want you to build [WHAT] using the Ollama analyzer suite and skeleton-driven development workflow.

Context:
- Project: Visual Audio — spatial compute OS + audio codec system
- Agent Constitution rules: [e.g., VCC compliance, formant-informed envelopes, 20ms symbol duration, CMUdict caching]
- Performance target: [specify if applicable, e.g., "4-6x speedup over QEMU", "maintain current throughput"]
- Verification gates: [e.g., codec roundtrip, dual-band encoding, VCC compliance tests]

Task:
[Describe what needs to be built in 1-2 sentences]

Requirements:
- [Specific requirement 1]
- [Specific requirement 2]
- [Specific requirement 3]

Use this workflow:

1. Generate skeleton using [generic/codec/tool/test/spatial] template
2. Implement core functionality:
   - [Component 1]
   - [Component 2]
   - [Component 3]
3. Run Ollama analysis iteratively:
   - First pass: architecture
   - Fix HIGH findings
   - Second pass: [performance if applicable]
   - Fix HIGH findings
   - Final pass: [security, style, testing as needed]
4. Run tests and verification gates:
   - [Test 1]
   - [Test 2]
   - [Test 3]
5. Mark ROADMAP task complete

Documentation:
- Save review documents: [list expected review files]
- Document [any specific concerns]

Priority:
- HIGH findings: must fix before proceeding
- MEDIUM findings: fix if time permits, document tradeoffs
- LOW findings: optional, defer if needed

Stop and ask me:
- Only if you genuinely have zero signal on product direction
- If you need explicit user approval for external actions (emails, tweets, etc.)
- Never ask for implementation choices — make the decision and proceed
```

---

## Tips for Good Prompts

**DO:**
- Be specific about what you want built
- Include performance targets if relevant
- Specify which template to use (generic/codec/tool/test/spatial)
- List verification gates (tests that must pass)
- Provide context about Visual Audio constraints

**DON'T:**
- Don't ask "how should I do this?" — just say "build X"
- Don't list implementation choices — let me decide
- Don't ask for confirmation on minor decisions
- Don't include "let me know if you need anything"

**Good example:**
- "Build a GPU-native RISC-V emulator with 4-6x speedup over QEMU, support addi/add/and/or/xor, use spatial template"

**Bad example:**
- "How should I build a RISC-V emulator? Should I use C or Python? What about GPU? Let me know what you think."

---

**To use this prompt:**
1. Copy the appropriate template (blank or example)
2. Fill in the brackets
3. Paste to me
4. I'll execute the workflow: skeleton → implement → analyze → verify → complete