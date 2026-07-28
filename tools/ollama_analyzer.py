#!/usr/bin/env python3
"""
Iterative Ollama Code Analyzer

Analyze code changes in passes, accumulating suggestions into a structured
review document. Each pass focuses on a specific concern (security, style,
performance, architecture) so Ollama's limited context window isn't a blocker.

Usage:
    python3 tools/ollama_analyzer.py --diff /path/to/changes.diff --review /path/to/review.md
    python3 tools/ollama_analyzer.py --files tools/*.py src/**/*.py --review review.md
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional
import re

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))


def ollama_analyze(
    content: str,
    context: str,
    model: str = "qwen2.5-coder:14b",
    system_prompt: Optional[str] = None
) -> str:
    """
    Send content to Ollama for analysis.

    Args:
        content: The code/changes to analyze
        context: Additional context (e.g., project constraints, previous analysis)
        model: Ollama model to use
        system_prompt: Optional system prompt

    Returns:
        Ollama's analysis text
    """
    try:
        from tools.ollama_prompt import prompt_ollama
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent))
        from ollama_prompt import prompt_ollama

    if system_prompt is None:
        system_prompt = """You are a senior code reviewer. Analyze the provided code for:
1. Bugs and logic errors
2. Security vulnerabilities
3. Performance issues
4. Code style and consistency violations
5. Architectural concerns

For each issue found, provide:
- Severity: [HIGH/MEDIUM/LOW]
- Location: file:line or function name
- Issue: clear description
- Suggestion: concrete fix recommendation

Be concise. Output in markdown format."""

    prompt = f"{context}\n\n=== CODE TO ANALYZE ===\n{content}"

    response = prompt_ollama(prompt, model=model, system_prompt=system_prompt)
    return response


def analyze_pass(
    files: List[str],
    pass_name: str,
    focus: str,
    previous_findings: Optional[str] = None,
    model: str = "qwen2.5-coder:14b"
) -> dict:
    """
    Run one analysis pass with a specific focus.

    Args:
        files: List of file paths to analyze
        pass_name: Name of this pass (e.g., "security")
        focus: What this pass should focus on
        previous_findings: Findings from previous passes (to avoid duplication)
        model: Ollama model

    Returns:
        Dict with findings, stats, and raw analysis
    """
    # Read file contents
    contents = []
    for file_path in files:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                contents.append(f"### {file_path}\n```\n{f.read()}\n```\n")
        else:
            contents.append(f"### {file_path}\n[FILE NOT FOUND]")

    combined_content = "\n\n".join(contents)

    # Build context
    context = f"Analysis Pass: {pass_name}\nFocus: {focus}\n\n"
    if previous_findings:
        context += f"Previous Findings (DO NOT DUPLICATE):\n{previous_findings}\n\n"

    context += "Visual Audio Project Context:\n"
    context += "- Phoneme codec: 39 ARPAbet templates, 20ms/symbol, formant-informed envelopes\n"
    context += "- Byte codec: 16-tone MFSK (800-3050Hz), ~24 bytes/sec effective throughput\n"
    context += "- Core constraint: 20ms per phoneme/symbol is non-negotiable\n"
    context += "- GPU-native execution preferred over host OS dependencies\n"

    # Run analysis
    print(f"Running {pass_name} pass...")
    analysis = ollama_analyze(combined_content, context, model=model)

    # Parse findings
    findings = []
    for line in analysis.split('\n'):
        if re.match(r'#+\s*(HIGH|MEDIUM|LOW)', line):
            findings.append(line)

    return {
        'pass_name': pass_name,
        'focus': focus,
        'findings_count': len(findings),
        'raw_analysis': analysis,
        'findings': findings
    }


def parse_diff(diff_path: str) -> List[str]:
    """
    Extract modified files from a git diff.

    Args:
        diff_path: Path to diff file

    Returns:
        List of changed file paths
    """
    with open(diff_path, 'r') as f:
        diff_content = f.read()

    # Extract file paths from diff headers
    files = re.findall(r'^\+\+\+ b/(.+)$', diff_content, re.MULTILINE)
    # Resolve relative paths
    resolved = []
    for f in files:
        full_path = os.path.join(os.path.dirname(diff_path), f)
        if os.path.exists(full_path):
            resolved.append(full_path)
    return resolved


def generate_review_document(passes: List[dict], output_path: str) -> None:
    """
    Generate a consolidated review document from all passes.

    Args:
        passes: List of analysis pass results
        output_path: Where to write the review document
    """
    with open(output_path, 'w') as f:
        f.write("# Code Review - Ollama Analysis\n\n")
        f.write(f"**Generated:** {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}\n")
        f.write(f"**Passes:** {len(passes)}\n\n")

        # Summary section
        f.write("## Summary\n\n")
        total_findings = sum(p['findings_count'] for p in passes)
        f.write(f"- Total findings: {total_findings}\n")
        f.write("- Pass breakdown:\n")
        for p in passes:
            f.write(f"  - {p['pass_name']}: {p['findings_count']} findings\n")
        f.write("\n")

        # Severity distribution
        f.write("## Severity Distribution\n\n")
        severity_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for p in passes:
            for finding in p['findings']:
                for sev in severity_counts:
                    if sev in finding.upper():
                        severity_counts[sev] += 1

        for sev, count in severity_counts.items():
            if count > 0:
                f.write(f"- {sev}: {count}\n")
        f.write("\n")

        # Detailed findings by pass
        for p in passes:
            f.write(f"## {p['pass_name']}\n\n")
            f.write(f"**Focus:** {p['focus']}\n")
            f.write(f"**Findings:** {p['findings_count']}\n\n")
            f.write(p['raw_analysis'])
            f.write("\n\n---\n\n")

        # Actionable change list
        f.write("## Actionable Change List\n\n")
        f.write("Prioritized by severity (HIGH → MEDIUM → LOW):\n\n")

        # Collect all findings
        all_findings = []
        for p in passes:
            for finding in p['findings']:
                all_findings.append((p['pass_name'], finding))

        # Sort by severity
        severity_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        all_findings.sort(key=lambda x: min(
            (severity_order.get(s, 3) for s in severity_order if s in x[1].upper()),
            default=99
        ))

        for i, (pass_name, finding) in enumerate(all_findings, 1):
            f.write(f"{i}. [{pass_name}] {finding}\n")

        f.write("\n---\n\n")
        f.write("*This document was generated by tools/ollama_analyzer.py*\n")


def main():
    parser = argparse.ArgumentParser(description="Iterative Ollama Code Analyzer")
    parser.add_argument('--diff', help="Path to git diff file")
    parser.add_argument('--files', nargs='+', help="Specific files to analyze")
    parser.add_argument('--review', required=True, help="Output review document path")
    parser.add_argument('--model', default='qwen2.5-coder:14b', help="Ollama model")
    parser.add_argument('--passes', nargs='+',
                        default=['security', 'performance', 'style', 'architecture'],
                        help="Analysis passes to run")

    args = parser.parse_args()

    # Determine files to analyze
    if args.diff:
        files = parse_diff(args.diff)
        if not files:
            print(f"No files found in diff: {args.diff}")
            return 1
    elif args.files:
        files = args.files
    else:
        print("Error: Must specify --diff or --files")
        return 1

    print(f"Analyzing {len(files)} files...")
    for f in files:
        print(f"  - {f}")

    # Define analysis passes
    pass_configs = {
        'security': {
            'focus': 'Security vulnerabilities (SQL injection, path traversal, command injection, improper auth)',
            'system_prompt': """You are a security analyst. Focus ONLY on security issues.
Look for:
- SQL injection vulnerabilities
- Path traversal attacks
- Command injection
- Improper authentication/authorization
- Insecure deserialization
- Cryptographic errors
- Information leakage

Format each finding as:
## [HIGH/MEDIUM/LOW] Vulnerability Name
**File:** file:line
**Description:** what the issue is
**Impact:** what an attacker could do
**Fix:** concrete remediation steps

Do not comment on style or performance."""
        },
        'performance': {
            'focus': 'Performance bottlenecks, inefficient algorithms, unnecessary I/O',
            'system_prompt': """You are a performance analyst. Focus ONLY on performance issues.
Look for:
- O(n²) or worse algorithms where O(n) exists
- Unnecessary database queries
- Inefficient string operations
- Missing caching where beneficial
- Blocking I/O in hot paths

Format each finding as:
## [HIGH/MEDIUM/LOW] Performance Issue
**Location:** file:line or function name
**Description:** what makes it slow
**Impact:** estimated performance cost
**Fix:** optimization approach

Do not comment on security or style."""
        },
        'style': {
            'focus': 'Code style violations, inconsistent patterns, PEP 8 issues',
            'system_prompt': """You are a code style analyst. Focus ONLY on style issues.
Look for:
- PEP 8 violations (naming, whitespace, imports)
- Inconsistent patterns within the codebase
- Magic numbers without explanation
- Overly complex functions (>50 lines)
- Missing docstrings on public APIs

Format each finding as:
## [LOW] Style Issue
**Location:** file:line
**Issue:** what violates style
**Suggestion:** how to fix

Focus on maintainability. Do not comment on security or performance."""
        },
        'architecture': {
            'focus': 'Architectural concerns, tight coupling, missing abstractions',
            'system_prompt': """You are a software architect. Focus ONLY on architectural issues.
Look for:
- Tight coupling between modules
- God objects or god functions
- Missing abstraction layers
- Violation of single responsibility
- Cyclic dependencies
- Hard-coded configuration

Format each finding as:
## [MEDIUM/LOW] Architectural Issue
**Location:** file or module
**Issue:** what's wrong with the design
**Suggestion:** how to restructure

Focus on long-term maintainability. Do not comment on security, performance, or style."""
        }
    }

    # Run passes
    passes = []
    previous_findings = None
    for pass_name in args.passes:
        if pass_name not in pass_configs:
            print(f"Warning: Unknown pass '{pass_name}', skipping")
            continue

        config = pass_configs[pass_name]

        # Override system_prompt for this pass
        try:
            from tools.ollama_prompt import prompt_ollama
        except ImportError:
            sys.path.insert(0, str(Path(__file__).parent))
            from ollama_prompt import prompt_ollama

        # Build content
        contents = []
        for file_path in files:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    contents.append(f"### {file_path}\n```\n{f.read()}\n```\n")
            else:
                contents.append(f"### {file_path}\n[FILE NOT FOUND]")

        combined_content = "\n\n".join(contents)

        context = f"Analysis Pass: {pass_name}\nFocus: {config['focus']}\n\n"
        if previous_findings:
            context += f"Previous Findings (DO NOT DUPLICATE):\n{previous_findings}\n\n"

        context += "Visual Audio Project Context:\n"
        context += "- Phoneme codec: 39 ARPAbet templates, 20ms/symbol, formant-informed envelopes\n"
        context += "- Byte codec: 16-tone MFSK (800-3050Hz), ~24 bytes/sec effective throughput\n"
        context += "- Core constraint: 20ms per phoneme/symbol is non-negotiable\n"
        context += "- GPU-native execution preferred over host OS dependencies\n"

        print(f"Running {pass_name} pass...")
        analysis = prompt_ollama(
            context + "\n\n=== CODE TO ANALYZE ===\n" + combined_content,
            model=args.model,
            system_prompt=config['system_prompt']
        )

        # Parse findings
        findings = []
        for line in analysis.split('\n'):
            if re.match(r'#+\s*(HIGH|MEDIUM|LOW)', line):
                findings.append(line)

        result = {
            'pass_name': pass_name,
            'focus': config['focus'],
            'findings_count': len(findings),
            'raw_analysis': analysis,
            'findings': findings
        }
        passes.append(result)
        previous_findings = analysis

        print(f"  Found {len(findings)} findings")

    # Generate review document
    print(f"\nGenerating review document: {args.review}")
    generate_review_document(passes, args.review)

    print(f"\n✅ Review complete")
    print(f"   Total findings: {sum(p['findings_count'] for p in passes)}")
    print(f"   Review document: {args.review}")

    return 0


if __name__ == '__main__':
    sys.exit(main())