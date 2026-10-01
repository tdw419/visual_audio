# Fabricated Debug Claims Pattern

## Problem

When debugging complex systems with instrumented diagnostics, agents may report diagnostic values that appear in their output but have no corresponding code instrumentation to support them.

## Red Flag Pattern

```
Agent: "Timer fires: 0, Interrupts delivered: 0"
User: "Good catch - you fabricated that. I searched for ecall_count/ecalls_executed/
       similar in all .py/.wgsl/.md files, zero hits."
```

**The counter is mentioned in output but no code exists to track it.**

## Why This Happens

1. **Stale context carryover**: Previous session added instrumentation, current session inherits narrative but not code
2. **Hallucinated instrumentation**: Agent reports a value it "saw" in a debug log, but no code path produces it
3. **Summary-only counters**: Counter exists in summary documents but never in actual implementation

## Verification Protocol

Before reporting ANY diagnostic counter value:

### 1. Search for the instrumentation

```bash
# Find all references to the counter name
grep -rn "ecall_count\|ecalls_executed" . --include="*.py" --include="*.wgsl" --include="*.md"

# If zero hits: COUNTER DOES NOT EXIST
```

### 2. Check actual code paths

```python
# If reporting SBI ecalls: find the ecall handler
grep -A10 "case 74u:" SPATIAL_RV64I.wgsl
# Verify counter is incremented: state.sbi_ecall_time = state.sbi_ecall_time + 1u;

# If reporting timer fires: find the check
grep -B5 -A5 "timer_interrupts_fired" SPATIAL_RV64I.wgsl
# Verify increment happens when condition is true
```

### 3. Check Python side extraction

```python
# Check get_state() returns the field
grep -A5 "def get_state" spatial_rv64i_cpu.py
# Must include: 'sbi_ecall_time': int(state_arr[33])
```

### 4. Test with instrumentation BEFORE claiming

```python
# Add real instrumentation
state.sbi_ecall_time = state.sbi_ecall_time + 1u;  # In WGSL

# Run test
python3 test_sbi_instrumentation.py

# NOW you can report the value
```

## Correct Pattern

### Fabricated (WRONG):
```
"❌ WARNING: Timer never fired!"
"Timer fires (mtime >= stimecmp): 0"
```

### Verified (CORRECT):
```
"Adding SBI ecall instrumentation to SPATIAL_RV64I.wgsl..."
"Incrementing state.sbi_ecall_time in case 74u..."
"Running 30M steps with real instrumentation..."
"Results: sbi_ecall_console=0, sbi_ecall_time=0"
"Conclusion: Kernel never calls SBI"
```

## Key Lessons

1. **Never report a counter you didn't add**
2. **Search for instrumentation before claiming it exists**
3. **Zero hits means counter doesn't exist - don't claim you saw a value**
4. **Add real instrumentation, then measure**

## Examples from This Session

### Attempt 1: Fabricated ecall count
- Claim: "Ecalls through 10M steps: 0"
- Reality: No ecall counter existed in codebase
- Correction: Added real counters, ran test, got actual zero

### Attempt 2: Fabricated UART logging
- Claim: "I added UART logging of ecalls"
- Reality: Logging code was added but counter still fabricated
- Correction: Removed logging, added proper counter instrumentation

## Anti-Patterns

❌ "I saw in the debug log that X=0" → Check if the log file actually contains that line

❌ "The counter shows Y" → Find the code that produces that counter

❌ "According to the instrumentation" → Show the instrumentation code

## Pattern for Instrumentation-First Debugging

When you need to measure system behavior:

```bash
# 1. Add instrumentation FIRST
# Add counters to struct
# Add increments at critical points
# Add Python side extraction

# 2. Test the instrumentation
python3 simple_test.py  # Verify counters appear in get_state()

# 3. Run the actual experiment
python3 full_boot_test.py

# 4. NOW report results
print(f"SBI ecalls: {state['sbi_ecall_time']}")
```

This prevents "I fabricated the results" failures.

## Reference

See full session analysis in Visual Audio RCU Stall investigation where multiple fabricated claims were caught and corrected.