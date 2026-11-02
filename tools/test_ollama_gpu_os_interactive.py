#!/usr/bin/env python3
"""Interactive GPU OS testing harness driven by local Ollama.

Workflow:
1. Prompts Ollama (qwen2.5-coder:7b) to generate a structured multi-phase test plan
   exercising the GPU OS (shell verbs, files, directories, navigation, pipes).
2. Executes each step against GlyphL1Shell and collects live outputs, timings, and CPU metrics.
3. Submits the full execution transcript back to Ollama for evaluation, compliance checking,
   and anomaly diagnosis.
4. Outputs a structured report and saves telemetry to .builder_queue/.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "experiments"))

from experiments.glyph_l1_shell import GlyphL1Shell

OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"
OUTPUT_FILE = REPO / "output" / "OLLAMA_INTERACTIVE_TEST_RESULT.json"


def query_ollama(prompt: str, model: str = MODEL_NAME, json_format: bool = True, timeout: float = 45.0) -> Optional[str]:
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if json_format:
        data["format"] = "json"

    req = urllib.request.Request(
        OLLAMA_ENDPOINT,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "")
    except Exception as exc:
        print(f"Ollama query failed: {exc}", file=sys.stderr)
        return None


def generate_test_plan() -> list[dict]:
    prompt = """You are an operating system QA engineer testing Geometry OS / Glyph OS (a GPU-native operating system shell with a real filesystem and pipe engine).
The shell supports these verbs:
- Directory management: mkdir <dir>, rmdir <dir>, cd <dir>, pwd
- File operations: echo <text> > <file>, echo <text> >> <file>, write <file> <text>, write >> <file> <text>, read <file>, cat <file>, rm <file>, rm -f <file>
- Coreutils: grep <pat> <file>, wc <file>, which <cmd>, env, time, date
- Pipes and Redirection: <producer> | <consumer> (e.g., cat <file> | grep <pattern>, cat <file> | wc), <consumer> < <file> (e.g., wc < <file>, grep <pat> < <file>)

Generate an 8-step test plan.
Rules:
1. One single command per step (do NOT use &&, ||, or semicolons).
2. If you cd into a directory, remember you must 'cd ..' back out before removing it with rmdir.
3. Include at least:
   - 1 directory creation and cd/pwd navigation
   - 1 file write and 1 append (>>)
   - 1 pipe command (e.g. cat file | grep text) or input redirection (<)
   - 1 safe cleanup (rm -f and cd .. / rmdir)

Return a JSON object with a 'test_plan' array:
{
  "test_plan": [
    {"step": 1, "cmd": "mkdir app_dir", "intent": "create test directory"},
    {"step": 2, "cmd": "...", "intent": "..."}
  ]
}
"""
    print(f"🤖 [1/3] Prompting Ollama ({MODEL_NAME}) to synthesize GPU OS test plan...")
    raw = query_ollama(prompt, model=MODEL_NAME, json_format=True)
    if not raw:
        raise RuntimeError("Failed to obtain test plan from Ollama")

    data = json.loads(raw)
    plan = data.get("test_plan") or data.get("steps") or data.get("cmds") or []
    return plan


def execute_test_plan(plan: list[dict]) -> tuple[GlyphL1Shell, list[dict]]:
    sh = GlyphL1Shell()
    results = []

    print(f"\n⚡ [2/3] Executing {len(plan)} test steps on live GPU OS substrate (GlyphL1Shell)...")
    for item in plan:
        step_num = item.get("step")
        cmd = item.get("cmd", "").strip()
        intent = item.get("intent", "")

        t0 = time.perf_counter()
        try:
            out = sh.turn(cmd)
        except Exception as exc:
            out = f"EXCEPTION:{type(exc).__name__}:{exc}"
        dur_ms = (time.perf_counter() - t0) * 1000.0

        cpu_faulted = sh.cpu.faulted
        cwd = sh.session.cwd_display

        status = "FAIL" if (cpu_faulted or (out.startswith("ERR") and "error" not in intent.lower()) or out.startswith("EXCEPTION")) else "OK"
        print(f"  [{status}] Step {step_num}: `{cmd}` ({dur_ms:.1f}ms) -> {out!r}")

        results.append({
            "step": step_num,
            "cmd": cmd,
            "intent": intent,
            "output": out,
            "duration_ms": dur_ms,
            "cpu_faulted": cpu_faulted,
            "cwd": cwd,
            "step_result": status,
        })

    return sh, results


def evaluate_results(plan: list[dict], results: list[dict]) -> dict:
    eval_prompt = f"""You are a senior OS architect reviewing a test execution transcript on Geometry OS / Glyph OS.
Here is the execution transcript:
{json.dumps(results, indent=2)}

Evaluate the test results:
1. Did each command behave as expected according to POSIX and Glyph OS specifications?
2. Did the pipe operator (|), file redirection, and directory navigation execute cleanly?
3. Did the GPU CPU maintain stability (no faults)?
4. Assign an overall grade (PASS / CONDITIONAL_PASS / FAIL) and provide a concise summary.

Return ONLY a JSON object:
{{
  "overall_verdict": "PASS | CONDITIONAL_PASS | FAIL",
  "score": "e.g. 8/8",
  "summary": "concise executive summary",
  "analysis_by_subsystem": {{
    "filesystem": "...",
    "pipe_engine": "...",
    "navigation": "...",
    "cpu_stability": "..."
  }},
  "recommendations": ["recommendation 1", "recommendation 2"]
}}
"""
    print(f"\n🧠 [3/3] Submitting transcript to Ollama ({MODEL_NAME}) for deep architectural evaluation...")
    raw = query_ollama(eval_prompt, model=MODEL_NAME, json_format=True, timeout=45.0)
    if not raw:
        return {"error": "Failed to get evaluation from Ollama"}
    return json.loads(raw)


def main():
    plan = generate_test_plan()
    sh, results = execute_test_plan(plan)
    evaluation = evaluate_results(plan, results)

    full_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "model": MODEL_NAME,
        "session_root": sh.session.root,
        "plan": plan,
        "execution": results,
        "ollama_evaluation": evaluation,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(full_payload, f, indent=2)

    print("\n" + "=" * 60)
    print("📊 OLLAMA GPU OS TEST VERDICT & RESULTS")
    print("=" * 60)
    print(f"Overall Verdict: {evaluation.get('overall_verdict')} ({evaluation.get('score')})")
    print(f"Executive Summary: {evaluation.get('summary')}")
    print("\nSubsystem Analysis:")
    for k, v in evaluation.get("analysis_by_subsystem", {}).items():
        print(f"  • {k.replace('_', ' ').title()}: {v}")
    if evaluation.get("recommendations"):
        print("\nRecommendations:")
        for r in evaluation.get("recommendations", []):
            print(f"  - {r}")
    print(f"\nArtifact saved to: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
