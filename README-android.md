# Android Local LLM Deployer

Deploy a quantized LLM on a Samsung S24 FE (Exynos 2400e) via USB,
exposing an OpenAI-compatible API at `localhost:8080`.

## Prerequisites

1. **ADB** installed on PC:
   ```bash
   sudo dnf install android-tools   # Fedora
   sudo apt install adb              # Debian/Ubuntu
   ```

2. **Phone setup** (one-time):
   - Settings > About Phone > tap "Build Number" 7 times
   - Settings > Developer Options > enable "USB Debugging"
   - Connect phone via USB, accept the authorization prompt

## Quick Start

```bash
python deploy_llm.py
```

That's it. The script will:
1. Verify ADB connection
2. Download llama.cpp Android server binary (~5 MB)
3. Download Gemma-2-2B-IT Q4 model (~1.5 GB)
4. Push both to the phone
5. Start the inference server
6. Set up port forwarding
7. Benchmark and print the endpoint URL

## Options

```
--model gemma-2-2b    Use Gemma 2 2B (default, 1.5 GB)
--model phi-3.5-mini  Use Phi 3.5 Mini (2.2 GB)
--port 8080           API port (default: 8080)
--skip-push           Files already on device, just start server
--skip-download       Files already in ./assets, just push & start
--lan                 Expose endpoint to LAN via socat
```

## Usage

```bash
# Default (Gemma 2B)
python deploy_llm.py

# Phi 3.5 Mini
python deploy_llm.py --model phi-3.5-mini

# Already pushed before, just restart
python deploy_llm.py --skip-push

# Expose to entire local network
python deploy_llm.py --lan
```

## Test the endpoint

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"local","messages":[{"role":"user","content":"Hello!"}]}'
```

## Stop

```bash
adb shell kill $(adb shell pidof llama-server)
adb forward --remove tcp:8080
```

## Expected Performance (S24 FE / Exynos 2400e)

| Model | Size | RAM Usage | Speed |
|-------|------|-----------|-------|
| Gemma-2-2B Q4 | 1.5 GB | ~2 GB | 15-25 tok/s |
| Phi-3.5-mini Q4 | 2.2 GB | ~3 GB | 10-18 tok/s |

## How it works

```
PC (Python)                    Samsung S24 FE
    |                               |
    |-- adb push llama-server ----->|  /data/local/tmp/mlc_llm/
    |-- adb push model.gguf ------>|  /sdcard/local_llm/
    |-- adb shell ./llama-server -->|  starts OpenAI-compat server
    |                               |  listening on :8080
    |-- adb forward tcp:8080 ----->|
    |                               |
    http://localhost:8080/v1/chat/completions
```

## File structure

```
android-llm/
  deploy_llm.py       # Main orchestration script
  assets/             # Downloaded binaries & models (auto-created)
    llama-server      # llama.cpp Android ARM64 binary
    gemma-2-2b-it-q4_k_m.gguf
```
