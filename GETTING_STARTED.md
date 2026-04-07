# Getting Started with Local LLMs

A practical guide for engineers who want to run LLMs locally — no cloud, no API keys, full privacy.

## Two paths

| | Phone (Android via USB) | PC / Bare Metal |
|---|---|---|
| **Hardware** | Any modern Android phone | Any x86_64 Linux box |
| **GPU needed?** | No (uses phone's NPU) | No (CPU works), GPU is faster |
| **Best for** | Demo, learning, portable | Real workloads, offloading tasks |
| **Speed** | 15-25 tok/s (2B model) | 30-100+ tok/s depending on hardware |
| **Setup time** | 5 min | 10 min |

---

## Option 1: Phone (Samsung / Pixel / any ARM64 Android)

See [deploy_llm.py](deploy_llm.py) — plug in your phone, run the script, get an API.

```bash
git clone https://github.com/amastbau/claude-workspace.git
cd claude-workspace/android-llm
python deploy_llm.py
```

---

## Option 2: PC / Bare Metal Server (recommended for real use)

### Step 1: Install Ollama (easiest way)

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

That's it. One command. Works on Linux, Mac, WSL.

### Step 2: Pull a model

```bash
# Small & fast (good for learning)
ollama pull gemma2:2b          # 1.6 GB, very fast

# Medium (good balance)
ollama pull llama3.1:8b         # 4.7 GB, great quality

# Large (if you have 16+ GB RAM)
ollama pull qwen2.5:14b         # 9 GB, excellent quality

# Coding-specific
ollama pull qwen2.5-coder:7b    # 4.7 GB, great for code tasks
```

### Step 3: Use it

**Chat (interactive):**
```bash
ollama run llama3.1:8b
```

**API (OpenAI-compatible):**
```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1:8b",
    "messages": [{"role": "user", "content": "Explain Kubernetes in 3 sentences"}]
  }'
```

**Python:**
```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="unused")

response = client.chat.completions.create(
    model="llama3.1:8b",
    messages=[{"role": "user", "content": "Write a Python function to parse YAML"}],
)
print(response.choices[0].message.content)
```

### Step 4: Expose to your network (optional)

```bash
# Edit the systemd service to listen on all interfaces
sudo systemctl edit ollama
```

Add:
```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```

Then:
```bash
sudo systemctl restart ollama
```

Now any machine on your LAN can hit `http://<your-ip>:11434/v1/chat/completions`.

---

## Which model should I pick?

| Use case | Model | Size | Why |
|----------|-------|------|-----|
| Learning / experiments | `gemma2:2b` | 1.6 GB | Tiny, fast, good enough to learn the API |
| General assistant | `llama3.1:8b` | 4.7 GB | Best quality at this size |
| Code generation | `qwen2.5-coder:7b` | 4.7 GB | Trained specifically on code |
| Summarization / analysis | `qwen2.5:14b` | 9 GB | Excellent comprehension |
| Maximum quality (32GB+ RAM) | `llama3.1:70b` | 40 GB | Near-cloud quality, needs beefy hardware |

### RAM rule of thumb
- **Q4 quantized model**: needs ~60% of parameter count in GB of RAM
- 7B model → ~5 GB RAM
- 14B model → ~10 GB RAM
- 70B model → ~42 GB RAM (need 64GB machine or GPU offload)

---

## GPU vs CPU — do I need a GPU?

**No.** All of these run on CPU. But GPU makes them faster:

| Hardware | 8B model speed |
|----------|---------------|
| CPU only (8 cores) | 8-15 tok/s |
| Nvidia RTX 3060 (12GB) | 40-60 tok/s |
| Nvidia RTX 4090 (24GB) | 80-120 tok/s |
| Apple M2 Pro | 30-50 tok/s |
| AMD RX 7900 XTX | 50-70 tok/s |

For learning and light use, CPU is perfectly fine.

---

## Offloading tasks to private metal instead of cloud

Once Ollama is running on your server, you can point any tool that supports OpenAI API to it:

### Use with Continue (VS Code AI assistant)
```json
// .continue/config.json
{
  "models": [{
    "provider": "ollama",
    "model": "qwen2.5-coder:7b",
    "apiBase": "http://your-server:11434"
  }]
}
```

### Use with Open WebUI (ChatGPT-like interface)
```bash
docker run -d -p 3000:8080 \
  -e OLLAMA_BASE_URL=http://your-server:11434 \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

Then open `http://localhost:3000` — full ChatGPT-style UI talking to your private server.

### Use with any Python script
```python
from openai import OpenAI

# Just point to your server instead of OpenAI
client = OpenAI(
    base_url="http://your-server:11434/v1",
    api_key="not-needed",
)
```

### Use with curl / shell scripts
```bash
# Drop-in replacement for OpenAI API
export OPENAI_API_BASE=http://your-server:11434/v1
export OPENAI_API_KEY=unused
```

---

## Quick comparison: Cloud vs Private Metal

| | Cloud (OpenAI/Anthropic) | Private Metal (Ollama) |
|---|---|---|
| Privacy | Data leaves your network | Data stays on your machine |
| Cost | Per-token billing | Free after hardware |
| Speed | Fast, but latency varies | Depends on your hardware |
| Quality | Best models available | Good, but smaller models |
| Internet needed | Yes | No |
| Best for | Production apps, best quality | Privacy, learning, cost control |

---

## AI Coding Tools That Work with Local Models

If you're used to Copilot or Claude Code, these tools give you a similar experience but can talk to your own local models (via Ollama, LM Studio, or any OpenAI-compatible endpoint):

| Tool | Type | Local model support | Feel |
|------|------|-------------------|------|
| **Continue** | VS Code extension | Yes (Ollama, any OpenAI-compat) | Inline autocomplete + chat |
| **Cline** | VS Code extension | Yes (Ollama, LM Studio, etc.) | Most Claude Code-like (agentic, edits files) |
| **aider** | CLI | Yes (Ollama, litellm) | Very similar to Claude Code CLI |
| **Tabby** | Self-hosted | Yes (runs its own models) | Copilot replacement, autocomplete |

### Recommended setup: Cline + Ollama

**Cline** is the closest to Claude Code — it can read/edit files, run terminal commands, and reason through multi-step tasks. To connect it to a local model:

1. Install the Cline extension in VS Code
2. Open Cline settings (`Ctrl+Shift+P` → "Cline: Open Settings")
3. Set provider to "OpenAI Compatible"
4. Configure:
   ```
   Base URL: http://localhost:11434/v1
   API Key:  not-needed
   Model:    qwen2.5-coder:7b
   ```

If the model runs on a remote server (or a phone via USB):
```
Base URL: http://<server-ip>:11434/v1
```

### Recommended setup: Continue (autocomplete + chat)

1. Install the Continue extension in VS Code
2. Edit `~/.continue/config.json`:
   ```json
   {
     "models": [{
       "title": "Local Qwen Coder",
       "provider": "ollama",
       "model": "qwen2.5-coder:7b",
       "apiBase": "http://localhost:11434"
     }],
     "tabAutocompleteModel": {
       "title": "Local Autocomplete",
       "provider": "ollama",
       "model": "qwen2.5-coder:1.5b",
       "apiBase": "http://localhost:11434"
     }
   }
   ```

### Realistic expectations

| Task | Local 7B model | Cloud (Claude/GPT-4) |
|------|---------------|----------------------|
| Autocomplete | Great | Great |
| Explain code | Good | Excellent |
| Write tests | Good | Excellent |
| Simple refactors | Good | Excellent |
| Multi-file refactors | Weak | Great |
| Complex debugging | Weak | Great |
| Architecture decisions | Poor | Great |

**Best hybrid approach:** Use a local model for autocomplete and quick tasks (cheap, private, fast), and Claude Code / cloud for complex multi-step work.

---

## Troubleshooting

```bash
# Check if Ollama is running
systemctl status ollama

# Check which models you have
ollama list

# Check resource usage while running
ollama ps

# View logs
journalctl -u ollama -f

# Kill a stuck model
ollama stop llama3.1:8b
```

---

*Last updated: 2026-04-08*
