#!/usr/bin/env python3
"""
test_vamp_executable_cartridges.py — Verify executable cartridges for VAMP.

Tests:
1. Cartridge generation (encode python script to dense PNG)
2. Sandboxed execution (via tools/dense_encoder.py run)
3. Consistency check result capture
4. Metadata persistence (execution_result, last_run_timestamp, consistency_check_status)
"""

import sys
import os
import json
import tempfile
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.dense_encoder import encode_dense, decode_dense, run_cartridge


def test_cartridge_generation_and_execution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        cartridge_png = tmp_path / "hello_world.png"
        
        # 1. Cartridge generation
        script_code = b"print('Hello from cartridge!')\nx = 10 * 5\nprint(f'Result: {x}')\n"
        
        encode_dense(script_code, str(cartridge_png), square=True)
        assert cartridge_png.exists()
        
        # 2. Decode verification
        recovered = decode_dense(str(cartridge_png))
        assert recovered == script_code
        
        # 3. Sandboxed execution directly via python API
        result = run_cartridge(str(cartridge_png), sandbox=True)
        
        assert result["execution_result"] == "SUCCESS"
        assert result["returncode"] == 0
        assert "Hello from cartridge!" in result["stdout"]
        assert "Result: 50" in result["stdout"]
        assert result["consistency_check_status"] == "PASS"
        assert "last_run_timestamp" in result
        
        # 4. Test failure case (script with error)
        error_png = tmp_path / "error.png"
        error_script = b"raise ValueError('Something broke')"
        encode_dense(error_script, str(error_png), square=True)
        
        err_result = run_cartridge(str(error_png), sandbox=True)
        
        assert err_result["execution_result"] == "FAILED"
        assert err_result["returncode"] != 0
        assert "ValueError: Something broke" in err_result["stderr"]
        assert err_result["consistency_check_status"] == "FAIL"
        
        # 5. Verify CLI works
        cli_proc = subprocess.run(
            [sys.executable, "tools/dense_encoder.py", "run", str(cartridge_png), "--sandbox"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent)
        )
        
        assert cli_proc.returncode == 0
        cli_json = json.loads(cli_proc.stdout)
        assert cli_json["execution_result"] == "SUCCESS"
        assert cli_json["consistency_check_status"] == "PASS"

        print("✓ Executable cartridge tests passed (generation, sandbox execution, metadata)")

if __name__ == "__main__":
    test_cartridge_generation_and_execution()
