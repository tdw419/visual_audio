"""Hackathon lane baseline gates — fast, no GPU, no boot."""
import hashlib, subprocess, pathlib, os, pytest

REPO = pathlib.Path(__file__).resolve().parents[2]   # visual_audio root
WT = pathlib.Path("/home/jericho/tmp/wt_hackathon_verify")
ASSET = pathlib.Path("/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin")
VENV_PY = "/home/jericho/zion/projects/visual_audio/venv/bin/python"
ASSET_MD5 = "0cad7ccf7111eef3c0bc1e903b947001"

def test_preverify_and_plan_docs_exist():
    for name in ("HACKATHON_META_APPLICATION.md", "HACKATHON_BUILD_PLAN.md",
                 "HACKATHON_DEMO_PREVERIFY_2026-10-20.md"):
        assert (REPO / name).is_file(), name

def test_canonical_kernel_asset():
    assert ASSET.is_file() and ASSET.stat().st_size == 67112960
    assert hashlib.md5(ASSET.read_bytes()).hexdigest() == ASSET_MD5

def test_worktree_healthy():
    assert WT.is_dir()
    assert (WT / "tools/boot_alpine_gpu_fixed.py").is_file()
    link = WT / "boot_images/alpine_riscv64.lnx.bin"
    assert link.exists(), "asset symlink missing in worktree"

def test_worktree_contains_preverify_baseline():
    """The pre-verify baseline (d77b9af4) must remain an ancestor of the worktree
    HEAD — forward work may advance HEAD, but the verified baseline may never
    leave the worktree's history."""
    sha = subprocess.run(["git", "-C", str(WT), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()
    if sha.startswith("d77b9af4") or sha == "d77b9af4":
        return  # exactly at baseline
    r = subprocess.run(["git", "-C", str(WT), "merge-base", "--is-ancestor",
                        "d77b9af4", "HEAD"], capture_output=True, text=True)
    assert r.returncode == 0, (
        f"worktree HEAD {sha[:12]} does not contain preverify baseline d77b9af4")

def test_venv_has_wgpu():
    r = subprocess.run([VENV_PY, "-c", "import wgpu"], capture_output=True)
    assert r.returncode == 0, r.stderr

def test_open_sbi_present():
    assert pathlib.Path("/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin").is_file()
