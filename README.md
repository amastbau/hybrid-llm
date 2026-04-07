# hybrid-llm

Run LLMs locally — on your phone, your PC, or both. No cloud, no API keys, full privacy.

## What's in here

| File | What it does |
|------|-------------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | Full guide: models, tools, setup, comparison |
| [deploy_llm.py](deploy_llm.py) | Script to deploy LLM on Android phone via USB |
| [README-android.md](README-android.md) | Android-specific setup details |

## Quick start

**PC (Ollama):**
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama run gemma2:2b
```

**Phone (Samsung S24 FE / any ARM64 Android):**
```bash
python deploy_llm.py
```

Both expose an OpenAI-compatible API at `http://localhost:<port>/v1/chat/completions`.

## The idea

Use cheap local hardware (phones, old PCs) to run small LLMs for routine tasks,
and save cloud API credits for the complex stuff. See [GETTING_STARTED.md](GETTING_STARTED.md)
for the full breakdown.
