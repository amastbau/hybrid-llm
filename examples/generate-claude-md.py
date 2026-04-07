#!/usr/bin/env python3
"""
Generate a CLAUDE.md for a project using a local LLM.

Instead of burning cloud tokens on boilerplate generation,
use a local model to analyze your project and draft the file.

Usage:
    python generate-claude-md.py /path/to/your/project

Requires: Ollama running locally (or any OpenAI-compatible endpoint)
    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull qwen2.5-coder:7b
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


DEFAULT_ENDPOINT = "http://localhost:11434/v1/chat/completions"
DEFAULT_MODEL = "qwen2.5-coder:7b"

# Token budget: keep the context small so local models stay fast
MAX_FILE_LINES = 30       # first N lines per file sample
MAX_FILES_SAMPLE = 15     # how many files to sample
MAX_TREE_DEPTH = 3        # directory tree depth


def get_tree(project_path: str) -> str:
    """Get a compact directory tree."""
    try:
        result = subprocess.run(
            ["tree", "-L", str(MAX_TREE_DEPTH), "--dirsfirst", "-I",
             "node_modules|.git|__pycache__|.venv|vendor|dist|build"],
            capture_output=True, text=True, cwd=project_path, timeout=10
        )
        lines = result.stdout.strip().splitlines()
        if len(lines) > 60:
            return "\n".join(lines[:60]) + "\n... (truncated)"
        return result.stdout.strip()
    except FileNotFoundError:
        return subprocess.run(
            ["ls", "-R"], capture_output=True, text=True,
            cwd=project_path, timeout=10
        ).stdout[:2000]


def get_git_info(project_path: str) -> str:
    """Get basic git info — cheap tokens."""
    parts = []
    for cmd, label in [
        (["git", "remote", "-v"], "Remotes"),
        (["git", "log", "--oneline", "-5"], "Recent commits"),
        (["git", "branch", "--list"], "Branches"),
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               cwd=project_path, timeout=5)
            if r.stdout.strip():
                parts.append(f"{label}:\n{r.stdout.strip()}")
        except Exception:
            pass
    return "\n\n".join(parts)


def sample_files(project_path: str) -> str:
    """Read first N lines of key files to understand the project."""
    key_patterns = [
        "Makefile", "Dockerfile", "docker-compose.yml",
        "package.json", "pyproject.toml", "setup.py", "go.mod",
        "requirements.txt", "Cargo.toml", "pom.xml",
        ".github/workflows/*.yml", "Jenkinsfile",
        "README.md", "CONTRIBUTING.md",
    ]

    samples = []
    seen = 0
    root = Path(project_path)

    # First grab known config files
    for pattern in key_patterns:
        for f in root.glob(pattern):
            if seen >= MAX_FILES_SAMPLE:
                break
            if f.is_file() and f.stat().st_size < 50_000:
                try:
                    lines = f.read_text(errors="ignore").splitlines()[:MAX_FILE_LINES]
                    samples.append(f"--- {f.relative_to(root)} ---\n" + "\n".join(lines))
                    seen += 1
                except Exception:
                    pass

    # Then sample some source files
    for ext in ["*.py", "*.go", "*.js", "*.ts", "*.java", "*.rs"]:
        for f in sorted(root.rglob(ext))[:3]:
            if seen >= MAX_FILES_SAMPLE:
                break
            if f.is_file() and ".git" not in str(f) and f.stat().st_size < 50_000:
                try:
                    lines = f.read_text(errors="ignore").splitlines()[:MAX_FILE_LINES]
                    samples.append(f"--- {f.relative_to(root)} ---\n" + "\n".join(lines))
                    seen += 1
                except Exception:
                    pass

    return "\n\n".join(samples)


def generate_claude_md(project_path: str, endpoint: str, model: str) -> str:
    """Send project context to local LLM and get CLAUDE.md draft."""

    tree = get_tree(project_path)
    git_info = get_git_info(project_path)
    file_samples = sample_files(project_path)

    # Build a focused prompt — every token counts on local models
    prompt = f"""Analyze this project and generate a CLAUDE.md file for it.

CLAUDE.md is a file that gives AI coding assistants (like Claude Code) context about the project.
It should include:
- Project name and one-line description
- How to build/run/test
- Key conventions (code style, naming, branch strategy)
- Important directories and what they contain
- Any non-obvious gotchas

Be concise. No fluff. Developers read this, not marketing.

PROJECT TREE:
{tree}

GIT INFO:
{git_info}

KEY FILES (first {MAX_FILE_LINES} lines each):
{file_samples}

Output ONLY the CLAUDE.md content in markdown. No explanation around it."""

    # Count approximate tokens (rough: 1 token ≈ 4 chars)
    input_chars = len(prompt)
    est_input_tokens = input_chars // 4
    print(f"  Input: ~{est_input_tokens} tokens ({input_chars} chars)")
    print(f"  Model: {model}")
    print(f"  Endpoint: {endpoint}")

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,  # CLAUDE.md should be short
        "temperature": 0.3,  # low creativity, high accuracy
    }).encode()

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    resp = urllib.request.urlopen(req, timeout=300)
    data = json.loads(resp.read().decode())

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    timings = data.get("timings", {})

    print(f"  Output: {usage.get('completion_tokens', '?')} tokens")
    if timings.get("predicted_per_second"):
        print(f"  Speed: {timings['predicted_per_second']:.1f} tok/s")
    print(f"  Total: {usage.get('total_tokens', '?')} tokens")
    print()

    # Show what this would have cost on cloud
    cloud_input_cost = usage.get("prompt_tokens", 0) * 3 / 1_000_000   # ~$3/M for Claude
    cloud_output_cost = usage.get("completion_tokens", 0) * 15 / 1_000_000  # ~$15/M
    cloud_total = cloud_input_cost + cloud_output_cost
    print(f"  Cloud cost (estimated): ${cloud_total:.4f}")
    print(f"  Local cost: $0.0000")

    return content


def main():
    parser = argparse.ArgumentParser(description="Generate CLAUDE.md using a local LLM")
    parser.add_argument("project_path", help="Path to the project directory")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                        help=f"OpenAI-compatible API endpoint (default: {DEFAULT_ENDPOINT})")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--write", action="store_true",
                        help="Write CLAUDE.md to the project directory (otherwise just prints)")
    args = parser.parse_args()

    project_path = os.path.abspath(args.project_path)
    if not os.path.isdir(project_path):
        print(f"ERROR: {project_path} is not a directory")
        sys.exit(1)

    print(f"\nGenerating CLAUDE.md for: {project_path}\n")

    content = generate_claude_md(project_path, args.endpoint, args.model)

    if args.write:
        out = os.path.join(project_path, "CLAUDE.md")
        with open(out, "w") as f:
            f.write(content + "\n")
        print(f"Written to: {out}")
        print("Review and edit before committing — local models aren't perfect!")
    else:
        print("=" * 60)
        print(content)
        print("=" * 60)
        print("\nRun with --write to save to CLAUDE.md")


if __name__ == "__main__":
    main()
