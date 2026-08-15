import json
import pytest
import os
import shutil
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from visual_git import VisualGit

@pytest.fixture
def repo_dir(tmp_path):
    repo = tmp_path / ".visual_git"
    yield repo
    if repo.exists():
        shutil.rmtree(repo)

@pytest.fixture
def vcs(repo_dir):
    return VisualGit(repo_dir=str(repo_dir))

def test_visual_git_init(vcs, repo_dir):
    vcs.init()
    assert (repo_dir / "objects").exists()
    assert (repo_dir / "refs").exists()
    assert (repo_dir / "HEAD").exists()

def test_visual_git_commit(vcs):
    vcs.init()
    
    tile_state = {
        "1": {"tile_id": 1, "word": "hello", "position": [10, 10]}
    }
    
    sha = vcs.commit("Initial commit", tile_state)
    assert sha is not None
    
    head = vcs.get_head()
    assert head == sha
    
    commit_data = vcs._read_object(sha)
    assert commit_data["message"] == "Initial commit"
    assert commit_data["type"] == "commit"

def test_visual_git_diff_move(vcs):
    vcs.init()
    
    state1 = {
        "1": {"tile_id": 1, "word": "hello", "position": [10, 10]}
    }
    vcs.commit("State 1", state1)
    
    state2 = {
        "1": {"tile_id": 1, "word": "hello", "position": [50, 50]}
    }
    vcs.commit("State 2", state2)
    
    diff_res = vcs.diff("HEAD~1", "HEAD")
    
    assert len(diff_res["moved"]) == 1
    assert diff_res["moved"][0]["tile_id"] == "1"
    assert diff_res["moved"][0]["from"] == [10, 10]
    assert diff_res["moved"][0]["to"] == [50, 50]
    
    assert len(diff_res["added"]) == 0
    assert len(diff_res["removed"]) == 0
    assert len(diff_res["modified"]) == 0

def test_visual_git_diff_add_remove_edit(vcs):
    vcs.init()
    
    state1 = {
        "1": {"tile_id": 1, "word": "hello", "position": [10, 10]},
        "2": {"tile_id": 2, "word": "world", "position": [20, 20]}
    }
    vcs.commit("State 1", state1)
    
    state2 = {
        "1": {"tile_id": 1, "word": "hallo", "position": [10, 10]},
        "3": {"tile_id": 3, "word": "new", "position": [30, 30]}
    }
    vcs.commit("State 2", state2)
    
    diff_res = vcs.diff("HEAD~1", "HEAD")
    
    assert len(diff_res["removed"]) == 1
    assert diff_res["removed"][0]["tile_id"] == 2
    
    assert len(diff_res["added"]) == 1
    assert diff_res["added"][0]["tile_id"] == 3
    
    assert len(diff_res["modified"]) == 1
    assert diff_res["modified"][0]["tile_id"] == "1"
    assert diff_res["modified"][0]["old_word"] == "hello"
    assert diff_res["modified"][0]["new_word"] == "hallo"
    
def test_visual_git_merge_conflict(vcs):
    vcs.init()
    
    base_state = {
        "1": {"tile_id": 1, "word": "hello", "position": [10, 10]}
    }
    base_sha = vcs.commit("Base", base_state)
    
    # Branch target
    (vcs.refs_dir / "feature").write_text(base_sha)
    
    # Commit to HEAD
    head_state = {
        "1": {"tile_id": 1, "word": "hello", "position": [20, 20]}
    }
    vcs.commit("Move to 20,20", head_state)
    
    # Commit to feature branch
    vcs.head_file.write_text("refs/feature")
    feature_state = {
        "1": {"tile_id": 1, "word": "hello", "position": [30, 30]}
    }
    vcs.commit("Move to 30,30", feature_state)
    
    # Try merging HEAD (which is now feature) with master
    res = vcs.merge("master")
    
    assert len(res["conflicts"]) == 1
    assert "1" in res["conflicts"]
    assert res["conflicts"]["1"]["HEAD"]["position"] == [30, 30]
    assert res["conflicts"]["1"]["TARGET"]["position"] == [20, 20]
