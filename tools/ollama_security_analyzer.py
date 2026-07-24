#!/usr/bin/env python3
"""
ollama_security_analyzer.py — Ollama-driven security analysis for Visual Audio containers.

TASK_A004: Uses Ollama to propose new attack vectors, verify existing mitigations,
and generate structured security reports.

Attack vector categories analyzed:
  - Code execution escape (sandbox bypass)
  - Container integrity (frame tampering, metadata corruption)
  - Data exfiltration (side channels, covert timing)
  - Denial of service (resource exhaustion, infinite decoding loops)
  - Audio injection (acoustic attacks via spectral codec)
  - PNG container attacks (steganography payload exploits)

Usage:
  python3 tools/ollama_security_analyzer.py --analyze         # Analyze codebase
  python3 tools/ollama_security_analyzer.py --propose          # Propose new vectors
  python3 tools/ollama_security_analyzer.py --verify-mitigations  # Check mitigations
  python3 tools/ollama_security_analyzer.py --full-report      # Full security report
"""

import argparse
import importlib.util
import inspect
import json
import os
import re
import sys
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VA_CONTAINER = os.environ.get("VA_CONTAINER", "visual_audio.mkv")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")

# Attack vector categories
ATTACK_CATEGORIES = {
    "code_execution_escape": {
        "name": "Code Execution Escape",
        "description": "Bypassing sandbox to execute arbitrary code on host",
        "severity": "CRITICAL",
    },
    "container_integrity": {
        "name": "Container Integrity",
        "description": "Tampering with container frames, metadata, or checksums",
        "severity": "HIGH",
    },
    "data_exfiltration": {
        "name": "Data Exfiltration",
        "description": "Unauthorized extraction of container or host data",
        "severity": "HIGH",
    },
    "denial_of_service": {
        "name": "Denial of Service",
        "description": "Resource exhaustion, infinite loops, decode bombs",
        "severity": "MEDIUM",
    },
    "audio_injection": {
        "name": "Audio Injection",
        "description": "Acoustic attacks via spectral codec or phoneme injection",
        "severity": "MEDIUM",
    },
    "steganography_abuse": {
        "name": "Steganography Abuse",
        "description": "Exploiting DCT/PNG steganography for payload obfuscation",
        "severity": "MEDIUM",
    },
}

# ---------------------------------------------------------------------------
# Ollama interface
# ---------------------------------------------------------------------------


def _prompt_ollama(prompt: str, system_prompt: Optional[str] = None) -> str:
    """Send a prompt to Ollama and return the response."""
    args = ["ollama", "run", DEFAULT_MODEL]
    full_prompt = f"System: {system_prompt}\n\n{prompt}" if system_prompt else prompt
    try:
        result = subprocess.run(
            args, input=full_prompt, capture_output=True, text=True,
            check=True, timeout=300,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError("Ollama timeout after 300 seconds")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Ollama failed: {e.stderr}")


# ---------------------------------------------------------------------------
# Codebase scanning
# ---------------------------------------------------------------------------


def scan_security_relevant_files() -> List[Path]:
    """Find files relevant to security analysis."""
    patterns = [
        "*sandbox*", "*security*", "*executor*", "*container*",
        "*encoder*", "*codec*", "*decode*",
    ]
    files = []
    for pattern in patterns:
        files.extend(PROJECT_ROOT.rglob(pattern))
    # Deduplicate and filter
    seen = set()
    unique = []
    for f in sorted(files):
        if f.is_file() and f not in seen:
            # Skip hidden dirs, venv, node_modules
            parts = f.relative_to(PROJECT_ROOT).parts
            if not any(p.startswith(".") or p in ("__pycache__", "venv", "node_modules") for p in parts):
                seen.add(f)
                unique.append(f)
    return unique


def find_known_mitigations() -> Dict[str, List[str]]:
    """Scan source for known security mitigation patterns."""
    mitigations = {}
    patterns = {
        "sandbox": [r"allowed_modules?|allowlist", r"blocked_modules?|blocked_imports?"],
        "resource_limits": [r"RLIMIT_", r"timeout", r"max_memory", r"max_concurrent"],
        "input_validation": [r"validate", r"santizie", r"check_bounds", r"guard"],
        "isolation": [r"subprocess\.Popen", r"containerize", r"namespace", r"chroot"],
        "crypto": [r"hashlib\.", r"sha256", r"CRC32", r"checksum"],
        "codec_safety": [r"try.*except", r"ValueError", r"assert.*len", r"not None"],
    }

    for category, regexes in patterns.items():
        matches = []
        for regex in regexes:
            result = subprocess.run(
                ["grep", "-rn", regex, str(PROJECT_ROOT / "tools"), str(PROJECT_ROOT / "src")],
                capture_output=True, text=True, timeout=30,
            )
            for line in result.stdout.strip().split("\n"):
                if line and "Binary" not in line:
                    matches.append(line.strip())
        if matches:
            mitigations[category] = matches[:10]  # cap at 10 per category

    return mitigations


# ---------------------------------------------------------------------------
# Attack vector generation (Ollama-based)
# ---------------------------------------------------------------------------


def _build_codebase_summary() -> str:
    """Build a concise summary of the codebase for Ollama context."""
    # Key files and their roles
    key_files = {
        "tools/va_container.py": "Single-file container manager (MKV/FFV1)",
        "tools/ollama_prompt.py": "Ollama integration for container self-audit",
        "tools/task_scheduler.py": "Container task scheduler using frame metadata",
        "tools/audit_loop.py": "Automated container self-audit loop",
        "tools/dense_encoder_sandbox.py": "Sandboxed code execution with import allowlist",
        "src/executor/sandbox.py": "SandboxedExecutor - resource limits, import blocking",
        "src/codec/dct_steganography.py": "DCT-based steganography for data embedding",
        "src/codec/fountain.py": "Fountain codes for lossy channel resilience",
        "tools/va_container.py": "run command executes code inside container frames",
    }
    lines = ["Codebase Security Summary:"]
    for path, role in key_files.items():
        full = PROJECT_ROOT / path
        exists = full.exists()
        size = full.stat().st_size if exists else 0
        lines.append(f"  {path} ({size} bytes, {'EXISTS' if exists else 'MISSING'}): {role}")
    return "\n".join(lines)


def _build_existing_mitigations_summary(mitigations: Dict[str, List[str]]) -> str:
    """Build a summary of existing mitigations for Ollama context."""
    lines = ["Existing Security Mitigations:"]
    for category, matches in mitigations.items():
        lines.append(f"\n[{category.upper()}]")
        for m in matches[:5]:
            lines.append(f"  {m}")
    return "\n".join(lines)


def propose_attack_vectors(
    category_filter: Optional[str] = None,
    count: int = 5,
    use_ollama: bool = True,
) -> List[Dict]:
    """Propose attack vectors for the Visual Audio container system.

    Args:
        category_filter: Optional category key to focus on.
        count: Number of attack vectors to propose.
        use_ollama: If True, use Ollama; otherwise return canned vectors for testing.

    Returns:
        List of attack vector dicts with keys: id, category, name, description,
        severity, existing_mitigation, suggested_test, exploitability.
    """
    if not use_ollama:
        return _generate_canned_vectors(category_filter, count)

    mitigations = find_known_mitigations()
    codebase_summary = _build_codebase_summary()
    mitigation_summary = _build_existing_mitigations_summary(mitigations)

    categories_to_analyze = [category_filter] if category_filter else list(ATTACK_CATEGORIES.keys())

    all_vectors = []
    for cat_key in categories_to_analyze:
        cat = ATTACK_CATEGORIES.get(cat_key, {})
        prompt = f"""You are a security researcher analyzing the Visual Audio container system.
Analyze this attack category and propose {count} specific, realistic attack vectors.

{codebase_summary}

{mitigation_summary}

Attack Category: {cat.get('name', cat_key)}
Severity: {cat.get('severity', 'MEDIUM')}
Description: {cat.get('description', '')}

For each attack vector, provide:
1. A specific attack name
2. A detailed technical description of the exploit
3. Whether existing mitigations would block it (YES/PARTIAL/NO)
4. A suggested test case to verify the attack or mitigation
5. Exploitability rating (EASY/MODERATE/DIFFICULT)

Output as JSON array with fields: name, description, existing_mitigation, suggested_test, exploitability
Return ONLY valid JSON, no other text."""

        try:
            response = _prompt_ollama(
                prompt,
                system_prompt="You are a security researcher. Output ONLY valid JSON arrays, no other text.",
            )
            # Extract JSON from response (handle markdown code blocks)
            json_str = response.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            vectors = json.loads(json_str)
            for v in vectors:
                v["category"] = cat_key
                v["severity"] = cat.get("severity", "MEDIUM")
                v["ollama_generated"] = True
            all_vectors.extend(vectors)
        except (json.JSONDecodeError, RuntimeError) as e:
            # Fallback to canned vectors for this category
            all_vectors.extend(_generate_canned_vectors(cat_key, count))

    return all_vectors[:count * len(categories_to_analyze)]


def _generate_canned_vectors(
    category_filter: Optional[str] = None,
    count: int = 3,
) -> List[Dict]:
    """Generate canned attack vectors for testing without Ollama.

    These are known attack patterns for MKV/FFV1/container systems.
    """
    canned = {
        "code_execution_escape": [
            {
                "name": "Sandbox import allowlist bypass via __import__",
                "description": "Python's __import__ builtin may not be blocked by import allowlisting. "
                               "An attacker can call __import__('os') to bypass the blocked_modules check.",
                "existing_mitigation": "PARTIAL",
                "suggested_test": "Test that `__import__('os').system('id')` is blocked in sandbox",
                "exploitability": "MODERATE",
            },
            {
                "name": "Sandbox escape via builtins overwrite",
                "description": "If the sandbox uses restricted_eval, builtins may still be accessible "
                               "through class hierarchies: ''.__class__.__mro__[1].__subclasses__()",
                "existing_mitigation": "NO",
                "suggested_test": "Verify no chain from string to subprocess.Popen",
                "exploitability": "EASY",
            },
        ],
        "container_integrity": [
            {
                "name": "FFV1 frame CRC bypass via crafted frame",
                "description": "A crafted FFV1 frame with valid CRC but malicious content could bypass "
                               "integrity checks if only CRC32 is verified.",
                "existing_mitigation": "PARTIAL",
                "suggested_test": "Insert a frame with valid CRC32 but modified payload and verify detection",
                "exploitability": "MODERATE",
            },
            {
                "name": "MKV metadata injection",
                "description": "Malicious metadata in MKV container could trigger XXE or injection "
                               "if XML parsing is used on MKV segment info.",
                "existing_mitigation": "NO",
                "suggested_test": "Inject metadata with XML entity and verify rejection",
                "exploitability": "MODERATE",
            },
        ],
        "data_exfiltration": [
            {
                "name": "Timing side channel via codec",
                "description": "A malicious cartridge could encode data in timing variations of "
                               "audio output, bypassing stdout restrictions.",
                "existing_mitigation": "NO",
                "suggested_test": "Sandbox should limit wall clock precision or add jitter",
                "exploitability": "DIFFICULT",
            },
        ],
        "denial_of_service": [
            {
                "name": "Decode bomb via fountain code expansion",
                "description": "Crafted fountain code parameters could cause exponential memory "
                               "allocation during decode, exhausting container resources.",
                "existing_mitigation": "PARTIAL",
                "suggested_test": "Fuzz fountain code decode with extreme parameters",
                "exploitability": "EASY",
            },
            {
                "name": "Deeply nested DCT block recursion",
                "description": "Maliciously crafted 8x8 DCT blocks could cause deep recursion "
                               "in IDCT computation, causing stack overflow.",
                "existing_mitigation": "NO",
                "suggested_test": "Verify DCT steganography has recursion depth limits",
                "exploitability": "EASY",
            },
        ],
        "audio_injection": [
            {
                "name": "Spectral aliasing codec bypass",
                "description": "High-amplitude out-of-band frequencies could alias into the "
                               "phoneme band, causing the decoder to interpret noise as commands.",
                "existing_mitigation": "PARTIAL",
                "suggested_test": "Inject high-amplitude noise at Nyquist frequency and verify rejection",
                "exploitability": "MODERATE",
            },
        ],
        "steganography_abuse": [
            {
                "name": "DCT DC coefficient flip during re-encode",
                "description": "A JPEG re-encode could flip DCT DC coefficient signs on purpose "
                               "to corrupt the embedded data payload without detection.",
                "existing_mitigation": "PARTIAL",
                "suggested_test": "Verify that flipped DC coefficients are detected as corruption",
                "exploitability": "DIFFICULT",
            },
        ],
    }

    result = []
    for cat_key, vectors in canned.items():
        if category_filter and cat_key != category_filter:
            continue
        cat = ATTACK_CATEGORIES.get(cat_key, {})
        for v in vectors[:count]:
            v["category"] = cat_key
            v["severity"] = cat.get("severity", "MEDIUM")
            v["ollama_generated"] = False
            result.append(v)
    return result


# ---------------------------------------------------------------------------
# Mitigation verification
# ---------------------------------------------------------------------------


def verify_mitigations() -> Dict:
    """Check that existing security mitigations are actually implemented.

    Returns a dict with verification results for each mitigation layer.
    """
    results = {}

    # 1. Sandbox import blocking
    sandbox_file = PROJECT_ROOT / "src" / "executor" / "sandbox.py"
    if sandbox_file.exists():
        content = sandbox_file.read_text()
        blocked = ""
        # Handle both "blocked" and "BLOCKLISTED" naming; prioritize structured names
        for keyword in ("BLOCKLISTED", "blocklist", "blocked_import", "blocked"):
            if keyword in content:
                start = content.find(keyword)
                # Try to find end boundary - look for next section
                next_keywords = ["ALLOWLISTED", "allowed", "allowlist"]
                end = len(content)
                for nk in next_keywords:
                    pos = content.find(nk, start + len(keyword))
                    if pos > 0 and pos < end:
                        end = pos
                blocked = content[start:end]
                break
        blocked_modules = re.findall(r"['\"](\w+)['\"]", blocked)
        results["sandbox_import_blocking"] = {
            "status": "PASS" if len(blocked_modules) > 10 else "WARN",
            "blocked_count": len(blocked_modules),
            "detail": f"Blocked {len(blocked_modules)} modules in sandbox.py",
        }
    else:
        results["sandbox_import_blocking"] = {
            "status": "FAIL",
            "blocked_count": 0,
            "detail": "sandbox.py not found",
        }

    # 2. Resource limits
    if sandbox_file.exists():
        has_rlimit = "RLIMIT" in content
        has_timeout = "timeout" in content.lower()
        results["resource_limits"] = {
            "status": "PASS" if (has_rlimit and has_timeout) else "WARN",
            "has_rlimit": has_rlimit,
            "has_timeout": has_timeout,
            "detail": "RLIMIT and timeout both present" if (has_rlimit and has_timeout) else f"RLIMIT={has_rlimit}, timeout={has_timeout}",
        }
    else:
        results["resource_limits"] = {"status": "FAIL", "detail": "sandbox.py not found"}

    # 3. Container checksum verification
    container_tool = PROJECT_ROOT / "tools" / "va_container.py"
    if container_tool.exists():
        content = container_tool.read_text()
        has_crc = "crc" in content.lower() or "CRC" in content
        has_sha256 = "sha256" in content.lower()
        has_verify = "verify" in content.lower()
        results["container_integrity"] = {
            "status": "PASS" if (has_crc and has_sha256) else "WARN",
            "has_crc": has_crc,
            "has_sha256": has_sha256,
            "has_verify_command": has_verify,
            "detail": f"CRC={has_crc}, SHA256={has_sha256}, verify={has_verify}",
        }
    else:
        results["container_integrity"] = {"status": "FAIL", "detail": "va_container.py not found"}

    # 4. Codec safety checks
    dct_file = PROJECT_ROOT / "src" / "codec" / "dct_steganography.py"
    if dct_file.exists():
        content = dct_file.read_text()
        has_error_handling = "try" in content and "except" in content
        has_bounds_check = "ValueError" in content or "assert" in content
        results["codec_safety"] = {
            "status": "PASS" if (has_error_handling and has_bounds_check) else "WARN",
            "has_error_handling": has_error_handling,
            "has_bounds_check": has_bounds_check,
            "detail": f"Error handling={has_error_handling}, bounds check={has_bounds_check}",
        }
    else:
        results["codec_safety"] = {"status": "FAIL", "detail": "dct_steganography.py not found"}

    # 5. Test coverage of security
    test_files = list((PROJECT_ROOT / "tests").glob("test_*security*"))
    test_files += list((PROJECT_ROOT / "tests").glob("test_*sandbox*"))
    test_files += list((PROJECT_ROOT / "tests").glob("test_*container*"))
    results["test_coverage"] = {
        "status": "PASS" if len(test_files) >= 3 else "WARN",
        "security_test_count": len(test_files),
        "detail": f"Found {len(test_files)} security-related test files",
    }

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(use_ollama: bool = True) -> Dict:
    """Generate a comprehensive security report.

    Args:
        use_ollama: Whether to use Ollama for attack vector generation.

    Returns:
        Report dict with metadata, mitigations, attack vectors, and recommendations.
    """
    report = {
        "timestamp": datetime.now().isoformat(),
        "project": "Visual Audio Container",
        "model": DEFAULT_MODEL if use_ollama else "canned",
        "summaries": {},
    }

    # 1. Verify existing mitigations
    report["mitigations"] = verify_mitigations()

    # 2. Propose attack vectors
    report["attack_vectors"] = propose_attack_vectors(
        use_ollama=use_ollama, count=3
    )

    # 3. Summarize findings
    mitigation_status = [(k, v) for k, v in report["mitigations"].items()]
    pass_count = sum(1 for _, v in mitigation_status if v.get("status") == "PASS")
    warn_count = sum(1 for _, v in mitigation_status if v.get("status") == "WARN")
    fail_count = sum(1 for _, v in mitigation_status if v.get("status") == "FAIL")

    severity_counts = {}
    for v in report["attack_vectors"]:
        sev = v.get("severity", "UNKNOWN")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    report["summaries"] = {
        "mitigation_pass": pass_count,
        "mitigation_warn": warn_count,
        "mitigation_fail": fail_count,
        "attack_vectors_total": len(report["attack_vectors"]),
        "attack_vectors_by_severity": severity_counts,
    }

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Ollama-driven security analysis for Visual Audio containers"
    )
    parser.add_argument("--analyze", action="store_true", help="Analyze codebase security")
    parser.add_argument("--propose", action="store_true", help="Propose new attack vectors")
    parser.add_argument("--verify-mitigations", action="store_true", help="Check existing mitigations")
    parser.add_argument("--full-report", action="store_true", help="Generate full security report")
    parser.add_argument("--category", choices=list(ATTACK_CATEGORIES.keys()), help="Focus on a specific category")
    parser.add_argument("--count", type=int, default=5, help="Number of attack vectors to propose")
    parser.add_argument("--model", type=str, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-ollama", action="store_true", help="Skip Ollama (use canned vectors)")
    parser.add_argument("--output", "-o", type=str, help="Output file for JSON report")
    args = parser.parse_args()

    model = args.model or DEFAULT_MODEL
    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model
    use_ollama = not args.no_ollama

    if args.analyze:
        print("=== Codebase Security Analysis ===")
        mitigations = find_known_mitigations()
        for category, matches in mitigations.items():
            print(f"\n[{category.upper()}] {len(matches)} pattern(s) found")
            for m in matches[:5]:
                print(f"  {m}")

    elif args.verify_mitigations:
        print("=== Mitigation Verification ===")
        results = verify_mitigations()
        for layer, result in results.items():
            status_symbol = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(result.get("status", "UNKNOWN"), "?")
            print(f"\n{status_symbol} {layer}")
            print(f"   Status: {result['status']}")
            print(f"   Detail: {result.get('detail', 'N/A')}")

    elif args.propose:
        print(f"=== Attack Vector Proposals ({'Ollama' if use_ollama else 'Canned'}) ===")
        vectors = propose_attack_vectors(
            category_filter=args.category,
            count=args.count,
            use_ollama=use_ollama,
        )
        for v in vectors:
            print(f"\n  [{v.get('severity', '?')}] {v.get('name', 'Unnamed')}")
            print(f"     Category: {v.get('category', '?')}")
            print(f"     Description: {v.get('description', 'N/A')[:120]}...")
            print(f"     Mitigation: {v.get('existing_mitigation', '?')}")
            print(f"     Exploitability: {v.get('exploitability', '?')}")

    elif args.full_report:
        print(f"=== Full Security Report ===")
        report = generate_report(use_ollama=use_ollama)
        print(f"\nTimestamp: {report['timestamp']}")
        print(f"Model: {report['model']}")
        print(f"\n--- Mitigations ---")
        for layer, result in report["mitigations"].items():
            sym = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(result.get("status", "?"), "?")
            print(f"  {sym} {layer}: {result['status']}")
        print(f"\n--- Attack Vectors ({report['summaries']['attack_vectors_total']} total) ---")
        for v in report["attack_vectors"]:
            print(f"  [{v.get('severity', '?')}] {v.get('name', 'Unnamed')}")
        print(f"\nSummary: {report['summaries']['mitigation_pass']} passed, "
              f"{report['summaries']['mitigation_warn']} warnings, "
              f"{report['summaries']['mitigation_fail']} failed")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\nReport saved to {args.output}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
