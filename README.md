# hybrid-llm

Run LLMs locally — on your phone, your PC, or both. No cloud, no API keys, full privacy.

## What's in here

| File | What it does |
|------|-------------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | Full guide: models, tools, setup, comparison |
| [deploy_llm.py](deploy_llm.py) | Script to deploy LLM on Android phone via USB |
| [README-android.md](README-android.md) | Android-specific setup details |

## Quick start

**PC/Server (Ollama):**
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama run gemma2:2b
```

**Phone (Samsung S24 FE / any ARM64 Android):**

Prerequisites: USB Debugging enabled, phone connected via USB, ADB installed ([setup guide](README-android.md))

```bash
python deploy_llm.py
# Downloads llama.cpp + Gemma 2B, pushes to phone, starts serving at localhost:8080
```

Both expose an OpenAI-compatible API at `http://localhost:<port>/v1/chat/completions`.

## Optimize phone for inference

Plug in your phone, open Claude Code from this folder, and run:
```
/phone-optimize
```

This kills Samsung/Google bloatware, dims screen, disables animations, and benchmarks inference. See [GETTING_STARTED.md](GETTING_STARTED.md#phone-performance-llm-service-mode) for details.

## Use with source-pad (RAG chatbot)

Index your code and ask questions using the phone LLM:
```bash
# In the source-pad project
LLM_PROVIDER=local source-pad index dir /path/to/your/code
LLM_PROVIDER=local source-pad serve
```

See [source-pad](https://github.com/amastbau/source-pad) for setup.

## The idea

Use cheap local hardware (phones, old PCs) to run small LLMs for routine tasks,
and save cloud API credits for the complex stuff. See [GETTING_STARTED.md](GETTING_STARTED.md)
for the full breakdown.
