#!/usr/bin/env python3
"""
audit_checker.py — Verify implementation status for ROADMAP tasks.

This tool checks whether the claimed implementation for a ROADMAP task
actually exists in the codebase. It uses AST parsing and static analysis
to avoid executing code while checking for function/class definitions.

Usage:
  python3 tools/audit_checker.py --task TASK_A001 --impl "tools/speak.py"
  python3 tools/audit_checker.py --help

Can be used standalone or called from the self-audit loop.
"""

import argparse
import ast
import json
import sys
from pathlib import Path


def parse_ast(file_path):
    """Parse a Python file into an AST, return None on error."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return ast.parse(content, filename=str(file_path))
    except Exception as e:
        print(f"ERROR: Failed to parse {file_path}: {e}", file=sys.stderr)
        return None


def check_for_name(tree, name):
    """Check if a name (function/class) is defined in the AST tree."""
    if not tree:
        return False

    class NameChecker(ast.NodeVisitor):
        def __init__(self, target_name):
            self.target_name = target_name
            self.found = False

        def visit_FunctionDef(self, node):
            if node.name == self.target_name:
                self.found = True
            self.generic_visit(node)

        def visit_ClassDef(self, node):
            if node.name == self.target_name:
                self.found = True
            self.generic_visit(node)

    checker = NameChecker(name)
    checker.visit(tree)
    return checker.found


def check_file_exists(file_path):
    """Check if a file exists and is readable."""
    path = Path(file_path)
    if not path.exists():
        return False, f"File not found: {file_path}"
    if not path.is_file():
        return False, f"Not a file: {file_path}"
    return True, "OK"


def check_python_syntax(file_path):
    """Check if a Python file has valid syntax."""
    tree = parse_ast(file_path)
    if tree is None:
        return False, f"Syntax error in {file_path}"
    return True, "OK"


def check_function_exists(file_path, function_name):
    """Check if a function is defined in a Python file."""
    tree = parse_ast(file_path)
    if tree is None:
        return False, f"Cannot parse {file_path}"
    if check_for_name(tree, function_name):
        return True, f"Function '{function_name}' found in {file_path}"
    return False, f"Function '{function_name}' not found in {file_path}"


def check_class_exists(file_path, class_name):
    """Check if a class is defined in a Python file."""
    tree = parse_ast(file_path)
    if tree is None:
        return False, f"Cannot parse {file_path}"
    if check_for_name(tree, class_name):
        return True, f"Class '{class_name}' found in {file_path}"
    return False, f"Class '{class_name}' not found in {file_path}"


def audit_implementation(impl_spec):
    """
    Audit an implementation specification.

    impl_spec can be:
    - A file path: "tools/speak.py"
    - A function: "tools/speak.py:encode"
    - A class: "tools/speak.py:Encoder"

    Returns a dict with audit results.
    """
    result = {
        "spec": impl_spec,
        "passed": False,
        "checks": [],
        "summary": ""
    }

    # Parse implementation spec
    if ":" in impl_spec:
        file_path, target = impl_spec.split(":", 1)
        target_is_class = target[0].isupper()
    else:
        file_path = impl_spec
        target = None
        target_is_class = False

    # Check file exists
    exists, msg = check_file_exists(file_path)
    result["checks"].append({"check": "file_exists", "passed": exists, "message": msg})
    if not exists:
        result["summary"] = msg
        return result

    # Check syntax for Python files
    if file_path.endswith(".py"):
        valid_syntax, msg = check_python_syntax(file_path)
        result["checks"].append({"check": "syntax_valid", "passed": valid_syntax, "message": msg})
        if not valid_syntax:
            result["summary"] = msg
            return result

        # Check for function or class if specified
        if target:
            if target_is_class:
                found, msg = check_class_exists(file_path, target)
            else:
                found, msg = check_function_exists(file_path, target)
            result["checks"].append({
                "check": "target_exists",
                "passed": found,
                "message": msg
            })
            result["summary"] = msg
            result["passed"] = found
        else:
            result["passed"] = True
            result["summary"] = f"File {file_path} exists and has valid syntax"
    else:
        result["passed"] = True
        result["summary"] = f"File {file_path} exists"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Audit ROADMAP task implementation status"
    )
    parser.add_argument(
        "--task",
        help="Task ID (e.g., TASK_A001) for reporting"
    )
    parser.add_argument(
        "--impl",
        required=True,
        help="Implementation specification: file[:function|class]"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit with 1 if audit fails, 0 otherwise"
    )

    args = parser.parse_args()

    # Run audit
    result = audit_implementation(args.impl)

    # Add task ID if provided
    if args.task:
        result["task_id"] = args.task

    # Output
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"Audit {status}: {result['spec']}")
        for check in result["checks"]:
            print(f"  [{check['check']}] {check['message']}")
        print(f"Summary: {result['summary']}")

    # Exit code
    if args.exit_code:
        sys.exit(0 if result["passed"] else 1)

    return 0


if __name__ == "__main__":
    sys.exit(main())