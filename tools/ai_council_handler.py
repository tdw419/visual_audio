#!/usr/bin/env python3
"""
ai_council_handler.py -- Multi-agent consensus and debate system.

When this structure receives governance directives, it executes them:
- debate: Run consensus process on a topic using multiple AI agents
- vote: Cast a vote on a proposal
- synthesize: Generate synthetic proposals from council deliberations

Usage (from container):
    va_container.py run visual_audio.mkv tools/ai_council_handler.py --directives
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_audio_container import Container


def read_governance_directives(container: Container, my_x: int, my_y: int) -> List[Tuple[str, Dict]]:
    """Read unconsumed governance directives addressed to this AI council.

    Returns (entry_name, content) pairs so callers can mark them consumed
    after execution -- without this, re-running the executor (e.g. in a
    scheduled loop) re-triggers every directive ever logged for this
    structure from scratch every time, including whole debate cascades.
    """
    all_gov = container.list(filter_role="governance")
    directives = []

    for e in all_gov:
        # Read directive content
        try:
            content = json.loads(container.read_text(e["name"]))
        except Exception:
            continue

        if content.get("consumed"):
            continue

        # Check if directive targets this structure
        target = content.get("target", "")
        if f"ai_council.py.{my_x}_{my_y}" in target:
            if content.get("action") in ("debate", "vote", "synthesize"):
                directives.append((e["name"], content))

    return directives


def mark_consumed(container: Container, name: str, content: Dict) -> None:
    """Mark a directive as executed so it won't be re-run on future passes."""
    content = dict(content)
    content["consumed"] = True
    content["consumed_at"] = time.time()
    container.update(name, json.dumps(content, indent=2).encode())

def issue_directive(container: Container, issuer_name: str, target: str, action: str, params: Dict):
    """Issue a new governance directive (cascading governance)."""
    directive = {
        "issuer": issuer_name,
        "target": target,
        "action": action,
        "params": params,
        "timestamp": __import__("time").time()
    }
    
    log_name = f"governance_{issuer_name}_{int(directive['timestamp']*1000)}"
    container.add(
        log_name,
        json.dumps(directive, indent=2).encode(),
        role="governance",
        note=f"Cascading directive issued by {issuer_name}"
    )
    print(f"    -> Issued cascading directive: {action} to {target}")


def find_neighbor_councils(container: Container, my_x: int, my_y: int, radius: int = 3) -> List[Dict]:
    """Find other AI councils nearby for multi-council deliberation."""
    all_arch = container.list(filter_role="architecture")
    neighbors = []

    for e in all_arch:
        if "ai_council" not in e["name"]:
            continue

        if "." in e["name"]:
            parts = e["name"].rsplit(".", 1)
            coord_str = parts[1] if len(parts) > 1 else ""
        else:
            continue

        try:
            x_str, y_str = coord_str.split("_")
            x, y = int(x_str), int(y_str)
        except (ValueError, AttributeError):
            continue

        # Include this council and nearby ones within radius
        dist = max(abs(x - my_x), abs(y - my_y))
        if dist <= radius:
            neighbors.append({
                "name": e["name"],
                "x": x,
                "y": y,
                "distance": dist,
            })

    return neighbors


def simulate_debate(topic: str, participants: int = 3) -> Dict:
    """Simulate a multi-agent debate on a topic.

    In a real system, this would spawn multiple LLM instances and have them
    reason about the topic, then synthesize a consensus. For now, we simulate
    the structure of the process.
    """
    import time
    import random

    # Simulate multiple agents presenting arguments
    agents = []
    for i in range(participants):
        stance = random.choice(["pro", "con", "neutral"])
        strength = random.uniform(0.5, 1.0)
        agents.append({
            "agent_id": f"agent_{i}",
            "stance": stance,
            "strength": strength,
            "argument": f"Argument {i}: {topic} is {'beneficial' if stance == 'pro' else 'problematic'}",
        })

    # Simulate consensus calculation
    pro_strength = sum(a["strength"] for a in agents if a["stance"] == "pro")
    con_strength = sum(a["strength"] for a in agents if a["stance"] == "con")

    if pro_strength > con_strength * 1.2:
        consensus = "approve"
    elif con_strength > pro_strength * 1.2:
        consensus = "reject"
    else:
        consensus = "neutral"

    return {
        "topic": topic,
        "participants": participants,
        "agents": agents,
        "pro_strength": pro_strength,
        "con_strength": con_strength,
        "consensus": consensus,
        "timestamp": time.time(),
    }


def execute_debate(container: Container, my_x: int, my_y: int, params: Dict, log_name_override: str = None) -> Dict:
    """Execute a debate directive."""
    topic = params.get("topic", "resource_allocation")
    consensus_threshold = params.get("consensus_threshold", 0.7)
    attempt = params.get("attempt", 1)
    radius = params.get("radius", 3)
    previous_participants = params.get("previous_participants", 0)

    print(f"  [ai_council] Debating topic: {topic} (Attempt {attempt})")

    # Find neighbor councils for multi-council deliberation
    neighbors = find_neighbor_councils(container, my_x, my_y, radius=radius)
    participants = len(neighbors)

    if participants < 2:
        print(f"    ⚠ Solo council (no neighbors for multi-agent debate)")
        participants = max(2, participants)

    print(f"    Participants: {participants}")

    # Simulate debate
    debate_result = simulate_debate(topic, participants)

    # Check consensus threshold
    total_strength = debate_result["pro_strength"] + debate_result["con_strength"]
    consensus_strength = max(debate_result["pro_strength"], debate_result["con_strength"]) / total_strength if total_strength > 0 else 0

    meets_threshold = consensus_strength >= consensus_threshold
    debate_result["meets_threshold"] = meets_threshold
    debate_result["consensus_strength"] = consensus_strength
    debate_result["threshold"] = consensus_threshold
    debate_result["attempt"] = attempt

    # Write debate log
    log_name = log_name_override or f"debate_log_{my_x}_{my_y}_{int(debate_result['timestamp'])}"
    container.add(
        log_name,
        json.dumps(debate_result, indent=2).encode(),
        role="governance",
        note=f"Debate on '{topic}' at AI council ({my_x}, {my_y})"
    )

    print(f"    ✓ Debate complete: consensus={debate_result['consensus']} ({consensus_strength:.2f})")

    # Cascading Governance: Re-debate logic
    if not meets_threshold:
        if attempt >= 5:
            print(f"    ✗ Hard cap reached (5 attempts). Consensus failed. Resolving to deterministic default: deferred.")
            debate_result["terminal_status"] = "deferred_due_to_cap"
        elif participants == previous_participants and attempt > 1:
            print(f"    ✗ Radius expansion ({radius}) yielded no new participants. Consensus failed. Resolving to deterministic default: deferred.")
            debate_result["terminal_status"] = "deferred_due_to_exhaustion"
        else:
            print(f"    [ai_council] Consensus not met. Cascading a re-debate directive (Attempt {attempt + 1}, Radius {radius + 1})")
            issue_directive(
                container,
                f"ai_council_{my_x}_{my_y}",
                f"ai_council.py.{my_x}_{my_y}",
                "debate",
                {
                    "topic": topic,
                    "consensus_threshold": consensus_threshold,
                    "attempt": attempt + 1,
                    "radius": radius + 1,
                    "previous_participants": participants,
                    "retry_of": log_name
                }
            )

    return debate_result


def execute_vote(container: Container, my_x: int, my_y: int, params: Dict) -> Dict:
    """Execute a vote directive on a proposal."""
    proposal_id = params.get("proposal_id", "unknown")
    vote = params.get("vote", "abstain")

    print(f"  [ai_council] Voting on proposal: {proposal_id}")

    vote_record = {
        "proposal_id": proposal_id,
        "council_x": my_x,
        "council_y": my_y,
        "vote": vote,
        "timestamp": __import__("time").time(),
    }

    # Write vote record
    log_name = f"vote_{proposal_id}_{my_x}_{my_y}"
    container.add(
        log_name,
        json.dumps(vote_record, indent=2).encode(),
        role="governance",
        note=f"Vote on {proposal_id}"
    )

    print(f"    ✓ Vote recorded: {vote}")

    return vote_record


def execute_synthesize(container: Container, my_x: int, my_y: int, params: Dict) -> Dict:
    """Execute a synthesize directive: generate new proposal."""
    source_topic = params.get("source", "resource_allocation")

    print(f"  [ai_council] Synthesizing proposal from: {source_topic}")

    # Read recent debates for context
    recent_debates = []
    all_gov = container.list(filter_role="governance")
    for e in all_gov[-10:]:  # Last 10 governance entries
        if "debate_log" in e["name"]:
            try:
                debate = json.loads(container.read_text(e["name"]))
                recent_debates.append(debate)
            except Exception:
                pass

    # Synthesize proposal based on debates
    synthesis = {
        "source_topic": source_topic,
        "proposal": f"Optimized {source_topic} based on {len(recent_debates)} deliberations",
        "rationale": "Synthesized from consensus patterns in recent debates",
        "confidence": 0.8 if recent_debates else 0.5,
        "timestamp": __import__("time").time(),
    }

    # Write synthesis
    log_name = f"synthesis_{my_x}_{my_y}_{int(synthesis['timestamp'])}"
    container.add(
        log_name,
        json.dumps(synthesis, indent=2).encode(),
        role="governance",
        note=f"Synthesized proposal at AI council ({my_x}, {my_y})"
    )

    print(f"    ✓ Synthesis complete: {synthesis['proposal']}")

    return synthesis


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AI council execution")
    parser.add_argument("--directives", action="store_true",
                       help="Execute all pending governance directives")
    parser.add_argument("--status", action="store_true",
                       help="Report current status")
    parser.add_argument("--x", type=int, default=None,
                       help="AI council X coordinate (auto-detected from directives if not provided)")
    parser.add_argument("--y", type=int, default=None,
                       help="AI council Y coordinate (auto-detected from directives if not provided)")
    args = parser.parse_args()

    import os
    va_container = os.environ.get("VA_CONTAINER", "visual_audio.mkv")

    with Container(va_container) as c:
        # Determine my coordinates
        my_x, my_y = args.x, args.y

        # If not provided, try to detect from directives
        if my_x is None or my_y is None:
            # Look for directives targeting any AI council, infer coordinates
            all_gov = c.list(filter_role="governance")
            for e in all_gov[-20:]:  # Check recent directives
                if "ai_council" in e["name"]:
                    try:
                        directive = json.loads(c.read_text(e["name"]))
                        target = directive.get("target", "")
                        # Parse: "ai_council.py.2_7"
                        if "ai_council" in target and "_" in target:
                            coord_part = target.rsplit("_", 1)[-1]
                            if "_" in coord_part:
                                coord_part = coord_part.replace(".py", "").replace(".json", "")
                                x_str, y_str = coord_part.split("_")
                                my_x, my_y = int(x_str), int(y_str)
                                break
                    except Exception:
                        continue

        if my_x is None or my_y is None:
            my_x, my_y = 0, 0
            print(f"Warning: Could not detect coordinates, defaulting to (0, 0)")

        print(f"=== AI Council at ({my_x}, {my_y}) ===")

        if args.status:
            # Find neighbor councils
            neighbors = find_neighbor_councils(c, my_x, my_y)
            print(f"Neighbor councils ({len(neighbors)}):")
            for n in neighbors:
                print(f"  • {n['name']} (dist={n['distance']})")

        elif args.directives:
            # Execute all pending directives
            directives = read_governance_directives(c, my_x, my_y)
            print(f"Found {len(directives)} directives")

            for idx, (name, directive) in enumerate(directives):
                print(f"\n  Executing directive {idx + 1}/{len(directives)}:")

                params = directive.get("params", {})

                if directive.get("action") == "debate":
                    result = execute_debate(c, my_x, my_y, params)

                elif directive.get("action") == "vote":
                    result = execute_vote(c, my_x, my_y, params)

                elif directive.get("action") == "synthesize":
                    result = execute_synthesize(c, my_x, my_y, params)

                mark_consumed(c, name, directive)

        else:
            # Default: show neighbors
            neighbors = find_neighbor_councils(c, my_x, my_y)
            print(f"Neighbor councils ({len(neighbors)}):")
            for n in neighbors:
                print(f"  • {n['name']} (dist={n['distance']})")


if __name__ == "__main__":
    main()