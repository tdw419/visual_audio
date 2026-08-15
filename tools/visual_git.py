#!/usr/bin/env python3
"""
Visual Version Control (TASK_I006)
Git commits expressed as tile movements. Provides before/after side-by-side rendering
of tile states and handles visual merge conflicts via tile manipulation.

Usage:
  python3 tools/visual_git.py commit -m "Move hello to top"
  python3 tools/visual_git.py diff HEAD~1 --visual
  python3 tools/visual_git.py merge other_branch
"""

import os
import json
import uuid
import hashlib
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any

class VisualGit:
    def __init__(self, repo_dir: str = ".visual_git"):
        self.repo_dir = Path(repo_dir)
        self.objects_dir = self.repo_dir / "objects"
        self.refs_dir = self.repo_dir / "refs"
        self.head_file = self.repo_dir / "HEAD"
        self.index_file = self.repo_dir / "index.json"
        
    def init(self):
        """Initialize the repository."""
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.refs_dir.mkdir(parents=True, exist_ok=True)
        if not self.head_file.exists():
            self.head_file.write_text("refs/master")
        if not (self.refs_dir / "master").exists():
            # Initial branch points nowhere
            pass
            
    def _hash_object(self, data: dict) -> str:
        content = json.dumps(data, sort_keys=True).encode('utf-8')
        return hashlib.sha1(content).hexdigest()
        
    def _read_object(self, sha: str) -> dict:
        path = self.objects_dir / sha
        if not path.exists():
            raise ValueError(f"Object {sha} not found")
        return json.loads(path.read_text())
        
    def _write_object(self, data: dict) -> str:
        sha = self._hash_object(data)
        (self.objects_dir / sha).write_text(json.dumps(data, indent=2))
        return sha

    def get_head(self) -> Optional[str]:
        if not self.head_file.exists():
            return None
        ref = self.head_file.read_text().strip()
        if ref.startswith("refs/"):
            ref_path = self.repo_dir / ref
            if ref_path.exists():
                return ref_path.read_text().strip()
            return None
        return ref

    def commit(self, message: str, tile_state: dict):
        """Commit the current tile state."""
        self.init()
        
        # Write tree object
        tree_sha = self._write_object({"type": "tree", "tiles": tile_state})
        
        # Get parent
        parent = self.get_head()
        
        # Write commit object
        commit_data = {
            "type": "commit",
            "tree": tree_sha,
            "message": message,
            "parents": [parent] if parent else []
        }
        commit_sha = self._write_object(commit_data)
        
        # Update HEAD
        ref = self.head_file.read_text().strip()
        if ref.startswith("refs/"):
            (self.repo_dir / ref).write_text(commit_sha)
        else:
            self.head_file.write_text(commit_sha)
            
        return commit_sha
        
    def resolve_revision(self, rev: str) -> str:
        """Resolve a revision string (e.g., HEAD, HEAD~1) to a SHA."""
        if rev == "HEAD":
            sha = self.get_head()
            if not sha:
                raise ValueError("HEAD is not pointing to a valid commit")
            return sha
            
        if rev.startswith("HEAD~"):
            count = int(rev.split("~")[1])
            sha = self.get_head()
            for _ in range(count):
                if not sha:
                    break
                commit = self._read_object(sha)
                parents = commit.get("parents", [])
                if not parents:
                    raise ValueError(f"Reached initial commit before resolving {rev}")
                sha = parents[0]
            return sha
            
        # Try as branch name
        branch_path = self.refs_dir / rev
        if branch_path.exists():
            return branch_path.read_text().strip()
            
        # Assume it's a SHA prefix
        for f in self.objects_dir.iterdir():
            if f.name.startswith(rev):
                return f.name
                
        raise ValueError(f"Could not resolve revision {rev}")

    def diff(self, rev1: str, rev2: str) -> dict:
        """Compute the visual diff (tile movements) between two revisions."""
        sha1 = self.resolve_revision(rev1)
        sha2 = self.resolve_revision(rev2)
        
        commit1 = self._read_object(sha1)
        commit2 = self._read_object(sha2)
        
        tree1 = self._read_object(commit1["tree"])
        tree2 = self._read_object(commit2["tree"])
        
        tiles1 = tree1.get("tiles", {})
        tiles2 = tree2.get("tiles", {})
        
        diff_grid = {
            "added": [],
            "removed": [],
            "moved": [],
            "modified": []
        }
        
        all_ids = set(tiles1.keys()) | set(tiles2.keys())
        
        for tid in all_ids:
            t1 = tiles1.get(tid)
            t2 = tiles2.get(tid)
            
            if t1 and not t2:
                diff_grid["removed"].append(t1)
            elif t2 and not t1:
                diff_grid["added"].append(t2)
            elif t1 and t2:
                # Check for movement
                pos1 = t1.get("position", [0, 0])
                pos2 = t2.get("position", [0, 0])
                
                word1 = t1.get("word", "")
                word2 = t2.get("word", "")
                
                is_moved = pos1 != pos2
                is_modified = word1 != word2
                
                if is_moved:
                    diff_grid["moved"].append({
                        "tile_id": tid,
                        "word": word2,
                        "from": pos1,
                        "to": pos2
                    })
                if is_modified:
                    diff_grid["modified"].append({
                        "tile_id": tid,
                        "old_word": word1,
                        "new_word": word2
                    })
                    
        return diff_grid
        
    def render_visual_diff(self, diff_result: dict):
        """Render the tile diff grid side-by-side."""
        print("=== VISUAL TILE DIFF GRID ===")
        if not any(diff_result.values()):
            print("No visual changes.")
            return
            
        if diff_result["added"]:
            print("\n[+] Added Tiles:")
            for t in diff_result["added"]:
                print(f"  + Tile {t['tile_id']} ('{t['word']}') at ({t['position'][0]}, {t['position'][1]})")
                
        if diff_result["removed"]:
            print("\n[-] Removed Tiles:")
            for t in diff_result["removed"]:
                print(f"  - Tile {t['tile_id']} ('{t['word']}') from ({t['position'][0]}, {t['position'][1]})")
                
        if diff_result["moved"]:
            print("\n[~] Moved Tiles:")
            for m in diff_result["moved"]:
                print(f"  ~ Tile {m['tile_id']} ('{m['word']}'): {m['from']} ➔ {m['to']}")
                
        if diff_result["modified"]:
            print("\n[*] Edited Tiles:")
            for m in diff_result["modified"]:
                print(f"  * Tile {m['tile_id']}: '{m['old_word']}' ➔ '{m['new_word']}'")
                
        print("=============================")

    def merge(self, target_branch: str) -> dict:
        """
        Merge target_branch into HEAD.
        Returns a dict of conflicts if any. Visual merge conflict resolution
        is represented by conflicting tile IDs.
        """
        head_sha = self.get_head()
        target_sha = self.resolve_revision(target_branch)
        
        # Simple three-way merge logic placeholder
        # Find LCA (Lowest Common Ancestor)
        # For simplicity in this visual git, we just compare HEAD and target
        # and assume any modified tile in BOTH branches is a conflict.
        
        commit_head = self._read_object(head_sha)
        commit_target = self._read_object(target_sha)
        
        tree_head = self._read_object(commit_head["tree"]).get("tiles", {})
        tree_target = self._read_object(commit_target["tree"]).get("tiles", {})
        
        conflicts = {}
        merged_tiles = {}
        
        all_ids = set(tree_head.keys()) | set(tree_target.keys())
        
        for tid in all_ids:
            h = tree_head.get(tid)
            t = tree_target.get(tid)
            
            if h and t:
                # If they are exactly the same, no conflict
                if h == t:
                    merged_tiles[tid] = h
                else:
                    conflicts[tid] = {"HEAD": h, "TARGET": t}
            elif h and not t:
                # Kept in HEAD, deleted in target -> conflict or delete depending on LCA
                # For our visual git, let's keep HEAD unless we do a full 3-way
                merged_tiles[tid] = h
            elif t and not h:
                # Added in target
                merged_tiles[tid] = t
                
        return {"conflicts": conflicts, "merged": merged_tiles}


def main():
    parser = argparse.ArgumentParser(description="Visual Version Control")
    subparsers = parser.add_subparsers(dest="command")
    
    # Init
    subparsers.add_parser("init", help="Initialize visual git repo")
    
    # Commit
    commit_parser = subparsers.add_parser("commit", help="Commit tile state")
    commit_parser.add_argument("-m", "--message", required=True)
    commit_parser.add_argument("--state", default="{}", help="JSON representation of tile state")
    
    # Diff
    diff_parser = subparsers.add_parser("diff", help="Diff two revisions")
    diff_parser.add_argument("rev1", nargs="?", default="HEAD~1")
    diff_parser.add_argument("rev2", nargs="?", default="HEAD")
    diff_parser.add_argument("--visual", action="store_true", help="Render visual diff grid")
    
    # Merge
    merge_parser = subparsers.add_parser("merge", help="Merge another branch")
    merge_parser.add_argument("branch")
    
    args = parser.parse_args()
    vcs = VisualGit()
    
    if args.command == "init":
        vcs.init()
        print("Initialized empty Visual Git repository")
        
    elif args.command == "commit":
        tiles = json.loads(args.state)
        sha = vcs.commit(args.message, tiles)
        print(f"[{sha[:7]}] {args.message}")
        
    elif args.command == "diff":
        diff_res = vcs.diff(args.rev1, args.rev2)
        if args.visual:
            vcs.render_visual_diff(diff_res)
        else:
            print(json.dumps(diff_res, indent=2))
            
    elif args.command == "merge":
        res = vcs.merge(args.branch)
        if res["conflicts"]:
            print("VISUAL MERGE CONFLICTS:")
            for tid, data in res["conflicts"].items():
                print(f"Tile {tid}:")
                print(f"  HEAD: {data['HEAD']}")
                print(f"  TARGET: {data['TARGET']}")
            print("\nPlease resolve conflicts visually using the tile editor.")
        else:
            print("Merge successful.")
            
if __name__ == "__main__":
    main()
