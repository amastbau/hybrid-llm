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


KNOWN_ENDPOINTS = [
    {"name": "Ollama", "url": "http://localhost:11434", "health": "/api/tags", "api": "/v1/chat/completions"},
    {"name": "Llama Stack", "url": "http://localhost:8321", "health": "/v1/models", "api": "/v1/chat/completions", "type": "llama-stack"},
    {"name": "Phone (USB)", "url": "http://localhost:8080", "health": "/health", "api": "/v1/chat/completions"},
    {"name": "Phone (alt)", "url": "http://localhost:8081", "health": "/health", "api": "/v1/chat/completions"},
    {"name": "LM Studio", "url": "http://localhost:1234", "health": "/v1/models", "api": "/v1/chat/completions"},
    {"name": "llama.cpp", "url": "http://localhost:8082", "health": "/health", "api": "/v1/chat/completions"},
]


def show_status():
    """Show all currently running LLM endpoints."""
    print()
    print("  Scanning for running LLM endpoints...")
    print()
    found = 0

    for ep in KNOWN_ENDPOINTS:
        try:
            resp = urllib.request.urlopen(ep["url"] + ep["health"], timeout=3)
            data = json.loads(resp.read().decode())

            models = []
            providers = []
            if "models" in data and not ep.get("type") == "llama-stack":
                # Ollama /api/tags format
                models = [m.get("name", "?") for m in data.get("models", [])]
            elif "data" in data:
                # OpenAI /v1/models or Llama Stack /v1/models format
                for m in data.get("data", []):
                    mid = m.get("id", "?")
                    meta = m.get("custom_metadata", {})
                    provider_id = meta.get("provider_id", "")
                    provider_res = meta.get("provider_resource_id", "")
                    if provider_id:
                        models.append(f"{mid}  (provider: {provider_id})")
                        if provider_id not in [p.get("id") for p in providers]:
                            providers.append({"id": provider_id, "resource": provider_res})
                    else:
                        models.append(mid)
            elif "status" in data:
                # llama.cpp /health format — check /v1/models for model info
                try:
                    mresp = urllib.request.urlopen(ep["url"] + "/v1/models", timeout=3)
                    mdata = json.loads(mresp.read().decode())
                    for m in mdata.get("data", []):
                        mid = m.get("id", "")
                        if mid:
                            meta = m.get("meta", {})
                            params = meta.get("n_params", 0)
                            size = meta.get("size", 0)
                            info = mid
                            if params:
                                info += f"  ({params/1e9:.1f}B params"
                                if size:
                                    info += f", {size/1e9:.1f}GB"
                                info += ")"
                            models.append(info)
                except Exception:
                    pass
                if not models:
                    models = ["(model loaded)"]

            status = "UP"
            label = ep['name']
            if ep.get("type") == "llama-stack":
                label += " (Llama Stack)"
            print(f"  {status:4s}  {label:25s}  {ep['url']}")
            print(f"        Endpoint: {ep['url']}{ep['api']}")
            if models:
                for m in models:
                    print(f"        Model:    {m}")
            if providers:
                # Show backend info for Llama Stack
                for p in providers:
                    try:
                        # Try to get provider config from Llama Stack /v1/providers
                        presp = urllib.request.urlopen(ep["url"] + "/v1/providers", timeout=3)
                        pdata = json.loads(presp.read().decode())
                        for prov in pdata.get("data", []):
                            if prov.get("provider_id") == p["id"]:
                                ptype = prov.get("provider_type", "")
                                pconfig = prov.get("config", {})
                                backend_url = pconfig.get("url", "")
                                print(f"        Provider: {p['id']} ({ptype})")
                                if backend_url:
                                    print(f"        Backend:  {backend_url}")
                                break
                    except Exception:
                        print(f"        Provider: {p['id']}")
            print()
            found += 1

        except Exception:
            pass

    if found == 0:
        print("  No running LLM endpoints found.")
        print()
        print("  Start one with:")
        print("    ollama serve                          # Ollama on :11434")
        print("    python deploy_llm.py                  # Phone on :8080")
        print("    lms server start                      # LM Studio on :1234")
    else:
        print(f"  {found} endpoint(s) found.")
    print()


def main():
    parser = argparse.ArgumentParser(description="Generate CLAUDE.md using a local LLM")
    subparsers = parser.add_subparsers(dest="command")

    # Default: generate command
    gen_parser = subparsers.add_parser("generate", help="Generate a CLAUDE.md for a project")
    gen_parser.add_argument("project_path", help="Path to the project directory")
    gen_parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                            help=f"OpenAI-compatible API endpoint (default: {DEFAULT_ENDPOINT})")
    gen_parser.add_argument("--model", default=DEFAULT_MODEL,
                            help=f"Model to use (default: {DEFAULT_MODEL})")
    gen_parser.add_argument("--write", action="store_true",
                            help="Write CLAUDE.md to the project directory (otherwise just prints)")

    # Status command
    subparsers.add_parser("status", help="Show currently running LLM endpoints")

    args = parser.parse_args()

    if args.command == "status":
        show_status()
    elif args.command == "generate":
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
    else:
        # No subcommand — show status by default
        show_status()


if __name__ == "__main__":
    main()
