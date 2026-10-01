#!/usr/bin/env python3
"""
faction_tracker.py -- Tracks each faction's "attention" position on the
spatial map: a 2D coordinate separate from anything it has built, moved
step-by-step toward a target, and consulted before a build directive is
allowed to claim a Hilbert-curve frontier tile.

This is the "travel costs time" layer of the Entropy War game design: a
faction can't just spam build directives at the frontier -- it has to
issue move_attention directives to walk its attention there first, at a
bounded Chebyshev step per turn.

State lives in a single container entry (role="faction"), updated via
Container.update() the same way governance directive consumption is
tracked -- see [[village_center_handler.py]] mark_consumed().
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_audio_container import Container

FACTION_STATE_ENTRY = "faction_state"
GAME_STATE_ENTRY = "game_state"
MAP_SIZE = 256  # per visual_audio.map.json: grid_side=256, capacity=65536
MAP_CAPACITY = MAP_SIZE * MAP_SIZE  # 65,536 tiles
VICTORY_THRESHOLD = 0.51  # 51% of map controls the game
VICTORY_TILES = int(MAP_CAPACITY * VICTORY_THRESHOLD)  # 33,424

DEFAULT_STEP = 4
DEFAULT_CLAIM_RADIUS = 1


def chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    return max(abs(ax - bx), abs(ay - by))


def load_factions(container: Container) -> Optional[Dict]:
    """Return the faction_state dict, or None if not yet initialized."""
    try:
        return container.read_json(FACTION_STATE_ENTRY)
    except KeyError:
        return None


def save_factions(container: Container, state: Dict) -> None:
    payload = json.dumps(state, indent=2).encode()
    if load_factions(container) is None:
        container.add(FACTION_STATE_ENTRY, payload, role="faction",
                       note="Entropy War faction attention/territory state")
    else:
        container.update(FACTION_STATE_ENTRY, payload)


def init_factions(container: Container, seeds: Dict[str, str]) -> Dict:
    """seeds: {faction_name: village_center_entry_name}.

    Reads each village_center's own (x, y) from its entry name
    (e.g. "village_center.py.8_8") and starts that faction's attention there.
    Refuses to re-initialize over existing state -- call reset_factions()
    explicitly if that's really what's wanted.
    """
    existing = load_factions(container)
    if existing is not None:
        raise ValueError("faction_state already exists; won't silently overwrite. "
                          "Use reset_factions() if you really want to restart the game.")

    factions = {}
    for name, seed_entry in seeds.items():
        try:
            coord_str = seed_entry.rsplit(".", 1)[1]
            x, y = (int(v) for v in coord_str.split("_"))
        except (IndexError, ValueError) as e:
            raise ValueError(f"can't parse coordinates from seed entry {seed_entry!r}") from e

        factions[name] = {
            "seed": seed_entry,
            "attention_x": x,
            "attention_y": y,
            "home_x": x,
            "home_y": y,
            "turns_used": 0,
            "structures": [seed_entry],
            "active_cascade": None,
        }

    state = {
        "factions": factions,
        "created": time.time(),
        "moves": 0,
        "claims": 0,
    }
    save_factions(container, state)
    return state


def reset_factions(container: Container, seeds: Dict[str, str]) -> Dict:
    """Force-restart faction state (existing state is preserved in update() history)."""
    factions = {}
    for name, seed_entry in seeds.items():
        coord_str = seed_entry.rsplit(".", 1)[1]
        x, y = (int(v) for v in coord_str.split("_"))
        factions[name] = {
            "seed": seed_entry, "attention_x": x, "attention_y": y,
            "home_x": x, "home_y": y, "turns_used": 0, "structures": [seed_entry],
            "active_cascade": None,
        }
    state = {"factions": factions, "created": time.time(), "moves": 0, "claims": 0}
    save_factions(container, state)
    return state


def faction_owning(state: Dict, structure_name: str) -> Optional[str]:
    """Which faction owns a given structure entry name (by exact/prefix match)."""
    for name, f in state["factions"].items():
        if structure_name in f["structures"]:
            return name
    return None


def faction_at(state: Dict, x: int, y: int) -> Optional[str]:
    """Which faction owns the village_center/structure closest to (x, y), if any is exactly there."""
    for name, f in state["factions"].items():
        if f["home_x"] == x and f["home_y"] == y:
            return name
    return None


MAX_CASCADE_ATTEMPTS = 20  # backstop; single-target convergence is proven bounded by
                            # ceil(distance/step), this only guards against future changes
                            # breaking that guarantee, not something expected to trigger


def get_active_cascade(state: Dict, faction: str) -> Optional[Dict]:
    return state["factions"][faction].get("active_cascade")


def try_start_cascade(state: Dict, faction: str, target_x: int, target_y: int) -> bool:
    """Claim the faction's attention for a move-then-build cascade toward
    (target_x, target_y).

    Returns True if this cascade now owns (or already owned) the faction's
    attention -- caller should issue move_attention + re-queue build.
    Returns False if a DIFFERENT cascade already owns the attention -- caller
    must not issue a competing move_attention (this is what prevents the
    livelock proven 2026-08-14: two simultaneous targets pulling the same
    attention in opposite directions every pass, oscillating forever while
    the governance log grows unbounded). Caller should just re-queue the
    build alone, unmoved, to retry once the active cascade clears.
    """
    f = state["factions"][faction]
    active = f.get("active_cascade")

    if active is not None and (active["target_x"], active["target_y"]) == (target_x, target_y):
        active["attempts"] += 1
        if active["attempts"] > MAX_CASCADE_ATTEMPTS:
            f["active_cascade"] = None
            return False  # give up on this cascade; let it fall through as abandoned
        return True

    if active is not None:
        return False  # a different cascade already owns this faction's attention

    f["active_cascade"] = {"target_x": target_x, "target_y": target_y, "attempts": 1}
    return True


def clear_active_cascade(state: Dict, faction: str, target_x: int, target_y: int) -> None:
    """Release the faction's attention claim once its cascade's target build
    succeeds (or is abandoned) -- only clears if it still matches, so an
    unrelated already-cleared/replaced cascade can't be stomped."""
    f = state["factions"][faction]
    active = f.get("active_cascade")
    if active is not None and (active["target_x"], active["target_y"]) == (target_x, target_y):
        f["active_cascade"] = None


def move_attention(state: Dict, faction: str, target_x: int, target_y: int,
                    step: int = DEFAULT_STEP) -> Dict:
    """Move one faction's attention up to `step` Chebyshev distance toward a target.

    Mutates state in place. Returns a small report: distance before/after,
    whether this move arrived within claim radius.
    """
    f = state["factions"][faction]
    ax, ay = f["attention_x"], f["attention_y"]
    dist_before = chebyshev(ax, ay, target_x, target_y)

    dx = max(-step, min(step, target_x - ax))
    dy = max(-step, min(step, target_y - ay))
    new_x, new_y = ax + dx, ay + dy

    f["attention_x"], f["attention_y"] = new_x, new_y
    f["turns_used"] += 1
    state["moves"] += 1

    dist_after = chebyshev(new_x, new_y, target_x, target_y)
    return {
        "faction": faction,
        "from": (ax, ay),
        "to": (new_x, new_y),
        "target": (target_x, target_y),
        "dist_before": dist_before,
        "dist_after": dist_after,
        "arrived": dist_after <= DEFAULT_CLAIM_RADIUS,
    }


def record_claim(state: Dict, faction: str, structure_name: str, container=None) -> None:
    state["factions"][faction]["structures"].append(structure_name)
    state["claims"] += 1
    
    # Check victory condition if container provided
    if container is not None:
        _check_victory(state, container)


def _check_victory(state: Dict, container) -> None:
    """Check if any faction controls 51% of the map.
    
    Writes game_state entry on victory, persisting the winner.
    No-op if game already ended.
    """
    # Skip if game already ended
    try:
        game_state = container.read_json(GAME_STATE_ENTRY)
        if game_state.get("winner"):
            return
    except KeyError:
        pass  # No game state yet, continue checking
    
    # Check each faction's coverage
    for faction, f_data in state["factions"].items():
        structures = len(f_data["structures"])
        if structures >= VICTORY_TILES:
            # Victory! Write game state
            game_state = {
                "winner": faction,
                "coverage": structures / MAP_CAPACITY,
                "structures_claimed": structures,
                "total_tiles": MAP_CAPACITY,
                "timestamp": time.time(),
            }
            payload = json.dumps(game_state, indent=2).encode()
            try:
                container.add(GAME_STATE_ENTRY, payload, role="game",
                             note=f"Victory: {faction} controls {game_state['coverage']:.1%} of map")
            except KeyError:
                # Game state already exists (race condition), update instead
                container.update(GAME_STATE_ENTRY, payload)
            print(f"\n{'='*60}")
            print(f"  VICTORY: {faction.upper()} WINS!")
            print(f"  Controls {structures:,} / {MAP_CAPACITY:,} tiles ({game_state['coverage']:.1%})")
            print(f"{'='*60}\n")
            return


def territory_report(state: Dict) -> Dict[str, int]:
    """Tile count per faction -- the crude score; contiguous-run scoring is
    a separate, richer pass over the Hilbert manifest, not implemented here."""
    return {name: len(f["structures"]) for name, f in state["factions"].items()}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Entropy War faction state")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="seed factions from existing village_center structures")
    pi.add_argument("container")
    pi.add_argument("--seed", action="append", required=True,
                     help="FactionName=village_center.py.X_Y, repeatable (2-4 times)")

    ps = sub.add_parser("status", help="show current faction state")
    ps.add_argument("container")

    pr = sub.add_parser("reset", help="clear cascade locks from stale cascades")
    pr.add_argument("container")

    args = parser.parse_args()

    with Container(args.container) as c:
        if args.cmd == "init":
            seeds = {}
            for s in args.seed:
                name, entry = s.split("=", 1)
                seeds[name] = entry
            state = init_factions(c, seeds)
            print(f"Initialized {len(state['factions'])} factions:")
            for name, f in state["factions"].items():
                print(f"  {name}: {f['seed']} at ({f['attention_x']}, {f['attention_y']})")

        elif args.cmd == "status":
            state = load_factions(c)
            if state is None:
                print("No faction game in progress (faction_state not found).")
                return
            print(f"Moves: {state['moves']}, Claims: {state['claims']}")
            for name, f in state["factions"].items():
                print(f"  {name}: attention=({f['attention_x']}, {f['attention_y']}) "
                      f"home=({f['home_x']}, {f['home_y']}) turns_used={f['turns_used']} "
                      f"structures={len(f['structures'])}")

        elif args.cmd == "reset":
            state = load_factions(c)
            if state is None:
                print("No faction game in progress (faction_state not found).")
                return

            cleared = 0
            for name, f in state["factions"].items():
                if f.get("active_cascade") is not None:
                    f["active_cascade"] = None
                    cleared += 1
                    print(f"  Cleared cascade lock for {name}")

            if cleared == 0:
                print("  No cascade locks to clear")
            else:
                save_factions(c, state)
                print(f"  Saved: {cleared} locks cleared")


if __name__ == "__main__":
    main()
