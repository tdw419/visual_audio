#!/usr/bin/env python3
"""
geos_archive — per-write archive retention (Glyph OS spine, SKELETON Phase 1/2).

PROBLEM (measured, DEFECT-20 ticket + ruling 2026-09-12 §Reserved item 3):
    tools/geos_emit.py publishes to ONE fixed filename (IMAGE_NAME +
    META_NAME). Every publish overwrites the previous, so the substrate keeps
    only the LAST writer. The write identity (write_id, writer) now exists
    (DEFECT-20), but nothing RETAINS the history those ids identify, and
    nothing bounds disk growth once per-write archives exist.

PURPOSE OF THIS MODULE
    Define the retention contract: given a set of archive records and a
    policy, decide deterministically which records survive and which are
    evicted. The DECISION is pure, stdlib-only and fully implemented here
    (it is a deterministic utility — see the skeleton rule that pure
    utilities ship implemented). The I/O that acts on the decision is
    STUBBED and belongs to the builder's fill-in pass.

DESIGN INVARIANTS (do not weaken without a ruling)
    I1  Determinism: retention_plan() is a pure function of (records, policy).
        Same inputs -> same eviction set, order included. A retention decision
        must be replayable, because in this repo a hash is a receipt.
    I2  No silent loss: every eviction must name its reason. A record is
        evicted only by a stated rule (superseded / over-count / over-bytes
        / policy-excluded), never by an unstated fallback.
    I3  Newest-wins is NOT the default. write_id is monotonic, so ordering is
        well-defined, but retention must be explicit about per-writer quotas:
        one noisy writer must not evict another writer's history.
    I4  Additive only: this module reads emit metadata; it never rewrites a
        committed image or sidecar in place.

BOUNDARY MAP
    geos_emit.publish()            geos_observation_server
        |  writes image+sidecar          |  reads a snapshot window
        |  (write_id, writer)            |
        v                                v
    +-------------------------------------------------------+
    |  geos_archive:  ArchiveRecord  ->  retention_plan()   |   <-- pure core
    |                        |                              |
    |                        v                              |
    |   ArchiveStore.plan() / .compact()   [STUB: I/O]      |
    +-------------------------------------------------------+
                             |
                             v
                   geos_registry: WriteRegistry   (cross-directory index)

PHASE STATUS
    Phase 1 (structure)  : done — types + signatures, compiles, no deps.
    Phase 2 (lock)       : done — invariants + intent comments above/below.
    Phase 3 (population) : TODO — ArchiveStore I/O bodies; see
                           systems/GLYPH_SPINE_SKELETON.md.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "ArchiveRecord",
    "RetentionPolicy",
    "Eviction",
    "retention_plan",
    "parse_record",
    "canonical_record_line",
]

# Eviction reasons — I2: every eviction names its rule.
REASON_SUPERSEDED = "superseded"
REASON_OVER_COUNT = "over-count"
REASON_OVER_BYTES = "over-bytes"
REASON_POLICY_EXCLUDED = "policy-excluded"


@dataclass(frozen=True)
class ArchiveRecord:
    """One published write, as identified by DEFECT-20 metadata.

    A record is the addressable unit of retention: it is what an operator
    points at when they say "keep this one". Frozen because a retention
    decision that mutates its inputs is not replayable (I1).
    """

    write_id: int
    writer: str
    image_path: str
    sidecar_path: str
    bytes_len: int = 0
    written_at: str = ""
    tags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RetentionPolicy:
    """Bounds on retained history. All limits are explicit; no implicit default.

    keep_per_writer : if set, each writer keeps at most this many records
                      (newest by write_id). Guards I3 — quota per writer.
    keep_total      : global cap on record count across all writers.
    max_bytes       : global cap on summed bytes_len (0 = unbounded).
    exclude_tags    : records carrying any of these tags are evicted
                      regardless of recency (e.g. scratch/probe artifacts).
    """

    keep_per_writer: Optional[int] = None
    keep_total: Optional[int] = None
    max_bytes: int = 0
    exclude_tags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Eviction:
    """A record to delete, with the rule that condemns it (I2)."""

    record: ArchiveRecord
    reason: str


def parse_record(sidecar: Dict[str, Any], image_path: str, sidecar_path: str) -> ArchiveRecord:
    """Build an ArchiveRecord from a surface.meta.json payload.

    Implemented: pure mapping with explicit validation. A sidecar without a
    write_id is not attributable, and an unattributable write must not enter
    the archive (DEFECT-20: 'unattributed' is a loud state, not a valid id).
    """
    if not isinstance(sidecar, dict):
        raise TypeError("sidecar must be a dict (parsed surface.meta.json)")
    raw_id = sidecar.get("write_id")
    if raw_id is None:
        raise ValueError("sidecar has no write_id: unattributable writes are not archived")
    try:
        write_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"write_id is not an integer: {raw_id!r}") from exc

    writer = sidecar.get("writer") or "unattributed"
    if not isinstance(writer, str):
        writer = "unattributed"

    tags = sidecar.get("tags") or ()
    if isinstance(tags, str):
        tags = (tags,)

    return ArchiveRecord(
        write_id=write_id,
        writer=writer,
        image_path=image_path,
        sidecar_path=sidecar_path,
        bytes_len=int(sidecar.get("bytes_len") or 0),
        written_at=str(sidecar.get("written_at") or ""),
        tags=tuple(str(t) for t in tags),
    )


def canonical_record_line(record: ArchiveRecord) -> str:
    """Canonical JSONL line for the registry index.

    Implemented: sorted keys, compact separators, no trailing whitespace.
    Determinism here is load-bearing — this repo treats a hash as a receipt,
    so two runs over the same record must produce identical bytes.
    """
    payload = {
        "bytes_len": record.bytes_len,
        "image_path": record.image_path,
        "sidecar_path": record.sidecar_path,
        "tags": list(record.tags),
        "write_id": record.write_id,
        "written_at": record.written_at,
        "writer": record.writer,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def retention_plan(
    records: Sequence[ArchiveRecord],
    policy: RetentionPolicy,
) -> List[Eviction]:
    """Decide which records to evict. PURE — the core of this module.

    Order of rules (each pass may condemn a record; a record is condemned
    once, by the FIRST rule that applies, so reasons stay unambiguous):

        pass 1  tag exclusion          -> REASON_POLICY_EXCLUDED
        pass 2  per-writer quota       -> REASON_SUPERSEDED
        pass 3  global count cap       -> REASON_OVER_COUNT
        pass 4  global byte cap        -> REASON_OVER_BYTES

    Survivors are chosen newest-first by write_id within each writer, so the
    policy never trades a newer write for an older one (I3).

    Returns evictions sorted by (write_id, image_path) for a stable, replayable
    order (I1). Never raises on empty input.
    """
    survivors: List[ArchiveRecord] = []
    evictions: List[Eviction] = []

    # pass 1 — explicit exclusion
    for rec in records:
        if policy.exclude_tags and any(t in policy.exclude_tags for t in rec.tags):
            evictions.append(Eviction(rec, REASON_POLICY_EXCLUDED))
        else:
            survivors.append(rec)

    # helper: newest-first within a group, tie-broken by path for determinism
    def newest_first(rows: Iterable[ArchiveRecord]) -> List[ArchiveRecord]:
        return sorted(rows, key=lambda r: (-r.write_id, r.image_path))

    # pass 2 — per-writer quota
    if policy.keep_per_writer is not None and policy.keep_per_writer >= 0:
        by_writer: Dict[str, List[ArchiveRecord]] = {}
        for rec in survivors:
            by_writer.setdefault(rec.writer, []).append(rec)
        kept: List[ArchiveRecord] = []
        for _writer, rows in sorted(by_writer.items()):
            ordered = newest_first(rows)
            kept.extend(ordered[: policy.keep_per_writer])
            for rec in ordered[policy.keep_per_writer:]:
                evictions.append(Eviction(rec, REASON_SUPERSEDED))
        survivors = kept

    # pass 3 — global count cap
    if policy.keep_total is not None and policy.keep_total >= 0:
        ordered = newest_first(survivors)
        survivors = ordered[: policy.keep_total]
        for rec in ordered[policy.keep_total:]:
            evictions.append(Eviction(rec, REASON_OVER_COUNT))

    # pass 4 — global byte cap
    if policy.max_bytes and policy.max_bytes > 0:
        ordered = newest_first(survivors)
        kept = []
        total = 0
        for rec in ordered:
            if total + rec.bytes_len <= policy.max_bytes:
                kept.append(rec)
                total += rec.bytes_len
            else:
                evictions.append(Eviction(rec, REASON_OVER_BYTES))
        survivors = kept

    return sorted(evictions, key=lambda e: (e.record.write_id, e.record.image_path))


@dataclass
class ArchiveStore:
    """I/O layer: turn a retention decision into filesystem effects.

    PHASE 3 TODO (builder) — bodies are stubs on purpose:
        __init__   : resolve archive_dir; do NOT create it (callers decide).
        plan()     : scan archive_dir for (image, sidecar) pairs; parse each
                     with parse_record(); return retention_plan(records, policy).
                     MUST be read-only — a plan that mutates is not a plan.
        compact()  : apply a plan. Delete evicted pairs; never touch records
                     absent from the plan; refuse if any evicted image is
                     referenced by the registry with a non-evicted sibling.
    """

    archive_dir: str
    registry: Optional["Any"] = None  # geos_registry.WriteRegistry, injected
    plan_cache: List[Eviction] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.plan_cache = []

    def plan(self, policy: RetentionPolicy) -> List[Eviction]:
        """Scan archive_dir for (image, sidecar) pairs and compute an eviction plan.

        Scans archive_dir recursively for candidate image files (.npy or .png),
        pairing each with an attributable sidecar in its own directory.
        A sidecar that exists but fails parse_record (e.g. no write_id) is skipped —
        such a write never entered the archive (parse_record's raise stays the
        writer-path gate). This is a deliberate rule, not an oversight.

        Read-only: does not modify, create, or touch the archive directory or files.
        Results are cached in self.plan_cache.
        """
        if not os.path.exists(self.archive_dir):
            self.plan_cache = []
            return []

        records: List[ArchiveRecord] = []

        # 1. Deterministic recursive walk of archive_dir (sorted order)
        for root, dirs, files in os.walk(str(self.archive_dir)):
            dirs.sort()
            files.sort()

            # 2. Candidate images: suffix .npy or .png in sorted order
            images = [f for f in files if f.endswith(".npy") or f.endswith(".png")]
            claimed_sidecars: set[str] = set()

            for img in images:
                image_path = os.path.join(root, img)
                stem, _ = os.path.splitext(img)

                # 3. Pairing rule: surface.meta.json if present, else <image-stem>.meta.json.
                # Precedent: mirrors tools/geos_observation_server.py:88-91.
                sidecar_candidates = ["surface.meta.json", f"{stem}.meta.json"]
                chosen_sidecar: Optional[str] = None
                for cand in sidecar_candidates:
                    if cand in files and cand not in claimed_sidecars:
                        chosen_sidecar = cand
                        break

                if chosen_sidecar is None:
                    # 4. An image with no available sidecar is skipped, never an exception.
                    continue

                # Claim the sidecar: one sidecar is claimed by at most one image.
                claimed_sidecars.add(chosen_sidecar)
                sidecar_path = os.path.join(root, chosen_sidecar)

                try:
                    with open(sidecar_path, "r", encoding="utf-8") as f:
                        sidecar_dict = json.load(f)
                    rec = parse_record(sidecar_dict, image_path=image_path, sidecar_path=sidecar_path)
                    records.append(rec)
                except (ValueError, TypeError, json.JSONDecodeError, OSError):
                    # 5. A sidecar that exists but fails parse_record (e.g. no write_id) is
                    # skipped — such a write never entered the archive (parse_record's raise
                    # stays the writer-path gate). Deliberate rule, not an oversight.
                    continue

        evictions = retention_plan(records, policy)
        self.plan_cache = evictions
        return evictions

    def _registry_refusal(self, plan: Sequence[Eviction]) -> Optional[str]:
        """Check for registry cross-reference conflict on partially-evicted keys.

        Returns an error message string if refusal triggers, or None.
        """
        entries = getattr(self.registry, "entries", None) or []
        if not entries:
            return None

        evicted_real_paths = set()
        for eviction in plan:
            for path in (eviction.record.image_path, eviction.record.sidecar_path):
                if path:
                    evicted_real_paths.add(os.path.realpath(str(path)))

        by_key: Dict[Tuple[str, int], List[Any]] = {}
        for entry in entries:
            k = getattr(entry, "key", None)
            if k is None:
                k = (getattr(entry, "origin_id", None), getattr(entry, "write_id", None))
            by_key.setdefault(k, []).append(entry)

        for key in sorted(
            by_key.keys(),
            key=lambda k: (str(k[0]), int(k[1])) if isinstance(k, tuple) and len(k) == 2 and isinstance(k[1], int) else str(k),
        ):
            group = by_key[key]
            if len(group) < 2:
                continue

            line_shas = {getattr(e, "line_sha", None) for e in group}
            if len(line_shas) <= 1:
                continue

            evicted_entries = []
            sibling_entries = []
            for e in group:
                img_path = getattr(e, "image_path", None)
                if img_path is not None and os.path.realpath(str(img_path)) in evicted_real_paths:
                    evicted_entries.append(e)
                else:
                    sibling_entries.append(e)

            if evicted_entries and sibling_entries:
                sorted_evicted = sorted(evicted_entries, key=lambda e: str(getattr(e, "image_path", "") or ""))
                sorted_sibling = sorted(sibling_entries, key=lambda e: str(getattr(e, "image_path", "") or ""))
                evicted_image_path = sorted_evicted[0].image_path
                sibling_image_path = sorted_sibling[0].image_path
                return (
                    f"refusing to compact: registry key {key!r} is partially evicted — "
                    f"non-evicted sibling {sibling_image_path} conflicts with "
                    f"evicted record {evicted_image_path} (distinct line_sha)"
                )

        return None

    def compact(self, plan: Sequence[Eviction]) -> Dict[str, int]:
        """Apply an eviction plan by deleting evicted (image, sidecar) file pairs.

        Delete set:
            The plan is the only authority. For each eviction in order, deletes
            record.image_path, then record.sidecar_path. No other files or
            directories are touched. No globbing, directory removal, or pattern
            deletion.

        Accounting units:
            Returns {"deleted": <n>, "bytes": <b>} where:
            - deleted: the number of individual files actually unlinked
              (not a record count; e.g. image+sidecar unlinked = 2).
            - bytes: measured on-disk size (os.path.getsize read before unlinking)
              summed over exactly those unlinked files.

        Idempotence:
            Missing paths are skipped without error (e.g. an already-applied plan
            or a partially-present pair). Applying the same plan a second time
            returns {"deleted": 0, "bytes": 0}.

        Containment refusal:
            Validates the entire plan before any file is deleted. Every path
            (image_path and sidecar_path) must resolve strictly inside
            archive_dir via os.path.realpath and os.path.commonpath. If any path
            escapes, raises ValueError naming the offending path and archive_dir,
            leaving the filesystem completely untouched.

        Boundary note:
            Step 3 implements the registry cross-reference refusal. Compact refuses
            (raises ValueError, deleting nothing) if the injected registry holds a
            conflicted key K = (origin_id, write_id) that is partially evicted:
            (1) registry has >=2 entries with key K;
            (2) entries carry >1 distinct line_sha (a genuine conflict);
            (3) at least one entry references an evicted artifact and at least one
                does not (non-evicted sibling).
            Linkage is by realpath(entry.image_path).
        """
        archive_real = os.path.realpath(str(self.archive_dir))

        # 1. Validate the WHOLE plan before deleting anything (containment fence).
        for eviction in plan:
            for path in (eviction.record.image_path, eviction.record.sidecar_path):
                path_real = os.path.realpath(str(path))
                try:
                    common = os.path.commonpath([archive_real, path_real])
                except ValueError:
                    common = ""
                if common != archive_real or path_real == archive_real:
                    raise ValueError(
                        f"refusing to compact outside archive_dir: {path} not under {self.archive_dir}"
                    )

        # Registry cross-reference refusal pass (before any deletion).
        refusal = self._registry_refusal(plan)
        if refusal is not None:
            raise ValueError(refusal)

        # 2. Delete, in the order the plan gives them, both files of each eviction.
        deleted_count = 0
        reclaimed_bytes = 0

        for eviction in plan:
            for path in (eviction.record.image_path, eviction.record.sidecar_path):
                try:
                    # Measured on-disk size read before unlinking. Not the sidecar-declared
                    # bytes_len: bytes_len is a policy input, while this is the disk
                    # actually reclaimed, and a retention tool must not report a number
                    # it did not measure.
                    file_size = os.path.getsize(path)
                    os.remove(path)
                    deleted_count += 1
                    reclaimed_bytes += file_size
                except FileNotFoundError:
                    # A path that does not exist is skipped, not fatal (idempotent).
                    continue

        return {"deleted": deleted_count, "bytes": reclaimed_bytes}


if __name__ == "__main__":  # Phase-1 smoke check: shape, not behaviour.
    demo = [
        ArchiveRecord(1, "stage-a", "a1.npy", "a1.json", bytes_len=10),
        ArchiveRecord(2, "stage-a", "a2.npy", "a2.json", bytes_len=10),
        ArchiveRecord(3, "stage-b", "b1.npy", "b1.json", bytes_len=10),
    ]
    evict = retention_plan(demo, RetentionPolicy(keep_per_writer=1))
    print(f"records={len(demo)} evictions={len(evict)}")
    for e in evict:
        print(f"  evict write_id={e.record.write_id} reason={e.reason}")
