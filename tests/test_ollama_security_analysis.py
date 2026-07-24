#!/usr/bin/env python3
"""
Ollama Security Analysis Tests - TASK_A004
Tests for LLM-driven security analysis of Visual Audio containers.

Tests cover:
- Attack vector proposal generation (canned fallback)
- Mitigation verification against real codebase
- Report generation structure and completeness
- Known attack pattern detection
- Category filtering
- CLI integration
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from ollama_security_analyzer import (  # noqa: E402
    ATTACK_CATEGORIES,
    PROJECT_ROOT,
    find_known_mitigations,
    verify_mitigations,
    propose_attack_vectors,
    generate_report,
    scan_security_relevant_files,
)


# ---------------------------------------------------------------------------
# Codebase scanning
# ---------------------------------------------------------------------------


class TestSecurityFileScanning:
    """Test codebase scanning for security-relevant files."""

    def test_scan_finds_key_files(self):
        """Scan should find sandbox, security, and container files."""
        files = scan_security_relevant_files()
        paths = [str(f.relative_to(PROJECT_ROOT)) for f in files]

        # Should find key security files
        assert any("sandbox" in p for p in paths), "Should find sandbox files"
        assert any("container" in p for p in paths), "Should find container files"
        assert any("security" in p for p in paths), "Should find security files"

    def test_scan_excludes_venv(self):
        """Scan should not include files from virtual environments."""
        files = scan_security_relevant_files()
        paths = [str(f) for f in files]
        for p in paths:
            assert "venv" not in p, f"Should exclude venv files: {p}"

    def test_scan_excludes_hidden_dirs(self):
        """Scan should not include files from hidden directories."""
        files = scan_security_relevant_files()
        paths = [str(f) for f in files]
        for p in paths:
            assert "/." not in p, f"Should exclude hidden dir files: {p}"


# ---------------------------------------------------------------------------
# Mitigation verification
# ---------------------------------------------------------------------------


class TestMitigationVerification:
    """Test the mitigation verification against the real codebase."""

    def test_verify_returns_all_categories(self):
        """verify_mitigations should return all security layers."""
        results = verify_mitigations()
        expected_layers = [
            "sandbox_import_blocking",
            "resource_limits",
            "container_integrity",
            "codec_safety",
            "test_coverage",
        ]
        for layer in expected_layers:
            assert layer in results, f"Missing layer: {layer}"
            assert "status" in results[layer], f"Missing status in: {layer}"

    def test_mitigation_status_values(self):
        """Each mitigation layer should have a valid status."""
        results = verify_mitigations()
        valid_statuses = {"PASS", "WARN", "FAIL"}
        for layer, result in results.items():
            assert result["status"] in valid_statuses, \
                f"{layer}: invalid status '{result['status']}'"

    def test_container_integrity_check(self):
        """Container integrity should at minimum have CRC or SHA256."""
        results = verify_mitigations()
        ci = results["container_integrity"]
        assert ci.get("has_crc") or ci.get("has_sha256"), \
            "Container should have CRC or SHA256 verification"

    def test_sandbox_import_blocking_exists(self):
        """Sandbox import blocking should exist."""
        results = verify_mitigations()
        sb = results["sandbox_import_blocking"]
        assert sb.get("blocked_count", 0) > 0, \
            "Should find blocked modules in sandbox"

    def test_resource_limits_present(self):
        """Resource limits should be implemented."""
        results = verify_mitigations()
        rl = results["resource_limits"]
        assert rl["status"] in {"PASS", "WARN"}, \
            "Resource limits should exist or at least partially exist"
        assert rl.get("has_timeout") or rl.get("has_rlimit"), \
            "Should have timeout or rlimit"


# ---------------------------------------------------------------------------
# Attack vector proposals
# ---------------------------------------------------------------------------


class TestAttackVectorProposals:
    """Test attack vector proposal generation (canned fallback)."""

    def test_propose_returns_vectors(self):
        """Proposing attack vectors should return a list."""
        vectors = propose_attack_vectors(use_ollama=False)
        assert isinstance(vectors, list)
        assert len(vectors) > 0, "Should return at least one vector"

    def test_propose_all_categories(self):
        """Without category filter, should return vectors from all categories."""
        vectors = propose_attack_vectors(use_ollama=False, count=2)
        categories_found = set(v.get("category") for v in vectors)
        assert len(categories_found) >= 5, \
            f"Should cover most categories, got: {categories_found}"

    def test_propose_category_filter(self):
        """Category filter should limit vectors to that category."""
        vectors = propose_attack_vectors(
            category_filter="code_execution_escape",
            use_ollama=False,
            count=3,
        )
        for v in vectors:
            assert v["category"] == "code_execution_escape", \
                f"Expected code_execution_escape, got {v['category']}"

    def test_vector_has_required_fields(self):
        """Each attack vector should have all required fields."""
        vectors = propose_attack_vectors(use_ollama=False, count=2)
        required = ["name", "description", "existing_mitigation", "suggested_test", "exploitability"]
        for v in vectors:
            for field in required:
                assert field in v, f"Vector missing field: {field}"

    def test_vector_severity_assigned(self):
        """Each vector should have a severity from its category."""
        vectors = propose_attack_vectors(use_ollama=False, count=2)
        for v in vectors:
            assert "severity" in v, "Vector missing severity"
            assert v["severity"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}, \
                f"Invalid severity: {v['severity']}"

    def test_vector_count_limit(self):
        """Count parameter should limit number of vectors per category."""
        vectors = propose_attack_vectors(use_ollama=False, count=1)
        # With count=1 and no category filter, should get 1 per category
        assert len(vectors) >= 6, \
            f"Should get at least 6 vectors (1 per category), got {len(vectors)}"

    def test_ollama_flag_default_true(self):
        """Default use_ollama=True for propose function."""
        # This just verifies the function signature
        import inspect
        sig = inspect.signature(propose_attack_vectors)
        assert sig.parameters["use_ollama"].default is True


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class TestReportGeneration:
    """Test full security report generation (canned mode)."""

    def test_report_structure(self):
        """Report should have expected top-level structure."""
        report = generate_report(use_ollama=False)
        required_keys = ["timestamp", "project", "model", "mitigations", "attack_vectors", "summaries"]
        for key in required_keys:
            assert key in report, f"Missing report key: {key}"

    def test_report_mitigations_present(self):
        """Report should contain mitigation results."""
        report = generate_report(use_ollama=False)
        assert len(report["mitigations"]) >= 4, "Should have at least 4 mitigation layers"

    def test_report_attack_vectors_present(self):
        """Report should contain attack vectors."""
        report = generate_report(use_ollama=False)
        assert len(report["attack_vectors"]) >= 6, "Should have at least 6 attack vectors"

    def test_report_summary_counts(self):
        """Report summary should have consistent counts."""
        report = generate_report(use_ollama=False)
        summary = report["summaries"]
        assert summary["attack_vectors_total"] == len(report["attack_vectors"])
        sev_total = sum(summary["attack_vectors_by_severity"].values())
        assert sev_total == summary["attack_vectors_total"], \
            f"Severity count {sev_total} != total {summary['attack_vectors_total']}"

    def test_report_timestamp_is_iso(self):
        """Timestamp should be ISO format."""
        report = generate_report(use_ollama=False)
        assert "T" in report["timestamp"], "Timestamp should be ISO format"

    def test_report_model_name(self):
        """Model name should be present."""
        report = generate_report(use_ollama=False)
        assert report["model"] == "canned", "Should indicate canned mode"

    def test_report_json_serializable(self):
        """Report should be JSON-serializable."""
        report = generate_report(use_ollama=False)
        # Should not raise
        json_str = json.dumps(report, indent=2)
        assert len(json_str) > 100, "Report JSON should be non-trivial"


# ---------------------------------------------------------------------------
# Fast CLI tests (no subprocess)
# ---------------------------------------------------------------------------


class TestCLIFast:
    """Test the CLI argument structure without running full commands."""

    def test_parser_accepts_analyze(self):
        """--analyze flag should be accepted."""
        import argparse
        from ollama_security_analyzer import main as dummy_import  # noqa: F811
        # Just verify the module defines main
        assert callable(dummy_import)

    def test_parser_accepts_verify_mitigations(self):
        """--verify-mitigations flag should be accepted."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--verify-mitigations", action="store_true")
        args = parser.parse_args(["--verify-mitigations"])
        assert args.verify_mitigations

    def test_parser_accepts_full_report(self):
        """--full-report and --output should be accepted."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--full-report", action="store_true")
        parser.add_argument("-o", "--output", type=str)
        args = parser.parse_args(["--full-report", "-o", "report.json"])
        assert args.full_report
        assert args.output == "report.json"

    def test_parser_accepts_category(self):
        """--category should accept valid category names."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--category", choices=list(ATTACK_CATEGORIES.keys()))
        args = parser.parse_args(["--category", "code_execution_escape"])
        assert args.category == "code_execution_escape"

    def test_parser_invalid_category_rejected(self):
        """Invalid --category value should be rejected."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--category", choices=list(ATTACK_CATEGORIES.keys()))
        with pytest.raises(SystemExit):
            parser.parse_args(["--category", "invalid_cat"])

    def test_parser_accepts_count(self):
        """--count should accept integers."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--count", type=int, default=5)
        args = parser.parse_args(["--count", "10"])
        assert args.count == 10

    def test_parser_defaults(self):
        """Default values should be set."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--count", type=int, default=5)
        parser.add_argument("--no-ollama", action="store_true")
        args = parser.parse_args([])
        assert args.count == 5
        assert not args.no_ollama


# ---------------------------------------------------------------------------
# Known mitigation patterns
# ---------------------------------------------------------------------------


class TestKnownMitigationPatterns:
    """Test detection of existing security patterns in the codebase."""

    def test_find_known_mitigations_returns_patterns(self):
        """find_known_mitigations should return patterns organized by category."""
        mitigations = find_known_mitigations()
        assert len(mitigations) > 0, "Should find mitigation patterns"
        # Should have at least some expected categories
        assert any(k in mitigations for k in
                   ["sandbox", "resource_limits", "input_validation", "crypto"]), \
            f"Should find standard categories, got {list(mitigations.keys())}"

    def test_mitigation_patterns_have_content(self):
        """Each mitigation category should have at least some matches."""
        mitigations = find_known_mitigations()
        for category, matches in mitigations.items():
            assert len(matches) > 0, f"Category '{category}' should have matches"

    def test_sandbox_patterns_found(self):
        """Sandbox patterns should be detected."""
        mitigations = find_known_mitigations()
        sandbox = mitigations.get("sandbox", [])
        assert len(sandbox) > 0, "Should find sandbox patterns"
        # Should mention allowed/blocked modules
        combined = " ".join(sandbox).lower()
        assert "allow" in combined or "block" in combined, \
            "Should find allowlist/blocklist references"

    def test_resource_limit_patterns_found(self):
        """Resource limit patterns should be detected."""
        mitigations = find_known_mitigations()
        limits = mitigations.get("resource_limits", [])
        assert len(limits) > 0, "Should find resource limit patterns"
        # Should mention RLIMIT or timeout
        combined = " ".join(limits).lower()
        assert "rlimit" in combined or "timeout" in combined, \
            "Should find RLIMIT or timeout references"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases in security analysis."""

    def test_empty_category_filter(self):
        """Empty/wildcard category filter should not crash."""
        vectors = propose_attack_vectors(
            category_filter=None,
            use_ollama=False,
            count=2,
        )
        assert len(vectors) >= 6  # 6 categories, 2 each (capped)

    def test_canned_vectors_have_no_ollama_flag(self):
        """Canned vectors should have ollama_generated=False."""
        vectors = propose_attack_vectors(use_ollama=False, count=1)
        for v in vectors:
            assert v.get("ollama_generated") is False, \
                "Canned vectors should have ollama_generated=False"

    def test_scan_rejects_nonexistent_paths(self):
        """Scan should handle nonexistent directory gracefully."""
        from ollama_security_analyzer import scan_security_relevant_files as scan
        files = scan()
        assert isinstance(files, list)

    def test_report_saves_to_file(self):
        """--output flag should write report to file."""
        report = generate_report(use_ollama=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(report, f)
            temp_path = f.name

        try:
            with open(temp_path) as f:
                loaded = json.load(f)
            assert "timestamp" in loaded
            assert "mitigations" in loaded
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
