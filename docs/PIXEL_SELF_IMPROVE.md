# Pixel Self-Improvement Loop

The `pixel_self_improve.py` script orchestrates a safe, bounded recursive self-improvement cycle for `visual_audio.mkv`. It leverages the `pixel-hermes` memory palace (via Ollama) to propose, verify, and implement exactly ONE scoped task per cycle.

## Crontab Deployment

To run this autonomously, add the following line to your crontab (`crontab -e`). This example runs the loop once every 4 hours at the top of the hour:

```bash
0 */4 * * * cd /home/jericho/projects/zion/projects/visual_audio && /usr/bin/env python3 tools/pixel_self_improve.py --once >> /tmp/pixel_self_improve.log 2>&1
```

## Safety Architecture

This script is built on extreme skepticism. AI self-reports are inherently unreliable unless verified by execution. The design constraints enforce this:

1. **Independent Verification**: Every proposal must supply a `verify_check` shell command. The check is run *before* implementation, and the output is passed to a second, independent LLM judge. If the gap doesn't exist, the cycle aborts.
2. **Blast-Radius Containment**: Work is done in an isolated git worktree branch (`pixel-self-improve/<timestamp>`), never on `master`.
3. **Execution Over Self-Report**: Post-implementation, the check runs again. If the judge evaluates the gap as still open, the implementation failed, and the cycle aborts.
4. **Mandatory Review**: Successful cycles commit to their isolated branch. A human must merge them into master. The loop does not self-authorize.
5. **Auditable Thoughts**: Every cycle outcome (success or failure) is written into `visual_audio.mkv` as a structured thought frame (`pixel_thought_<timestamp>`).

6. **No leaks on failure**: every non-committed exit path (rejected proposal,
   gap judged not real, implementation failed to close the gap, syntax gate
   failed, commit failed) removes its worktree and branch immediately. Found
   this the hard way on first real test: the original version only cleaned
   up in `--dry-run` mode, which would have leaked a worktree+branch on
   every single rejected cycle when run unattended — most cycles are
   expected to be rejected (that's the design working), so this would have
   been the common case, not an edge case. Fixed and re-verified across
   three real failure runs before trusting it.

## Forbidden Zones

The agent is strictly prevented from touching high-risk files or directories (e.g., `.git/`, `.rts/`, `va_container.py`). Any proposal targeting these paths is immediately rejected by the script.

## Known limitation: the judge is not fully deterministic

The independent judge step (a second Ollama call deciding REAL vs.
ALREADY_DONE from the same check output) is not perfectly reliable. In
testing, the exact same real, unclosed gap (multi-modal context retrieval,
`verify_check` output `0`) was judged REAL in one run and NOT REAL in
another, with identical inputs. It's a genuine gate — it did correctly
catch a hallucinated target file and a no-op fake implementation in
testing — but it will also sometimes reject real, valid work. This is a
soft loop (low proposal acceptance rate is expected and safe), not a
guarantee of consistent judgment. Do not treat a single rejected cycle as
proof a gap doesn't exist, and do not treat a single accepted cycle as
proof the judge is reliable — review the actual diff on the review branch
either way.
