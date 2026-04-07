#!/usr/bin/env python3
"""
Android Local LLM Deployer
===========================
Automates deployment of a quantized LLM on a Samsung S24 FE (Exynos 2400e)
via ADB, and exposes an OpenAI-compatible API endpoint over USB port forwarding.

Usage:
    python deploy_llm.py [--model MODEL_PATH] [--port PORT] [--skip-push]

Requirements:
    - ADB installed and in PATH
    - USB Debugging enabled on the phone
    - Phone connected via USB
    - MLC LLM APK + model weights downloaded (see DOWNLOADS section below)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

DEFAULT_PORT = 8080
DEVICE_MODEL_DIR = "/sdcard/local_llm"
DEVICE_BIN_DIR = "/data/local/tmp/mlc_llm"

# MLC LLM Android server binary (CLI, no APK needed)
MLC_LLM_RELEASE = "https://github.com/mlc-ai/binary-mlc-llm-libs/releases/latest"

# Recommended models (GGUF for llama.cpp / MLC format for MLC LLM)
MODELS = {
    "gemma-2-2b": {
        "name": "Gemma-2-2B-IT-Q4_K_M",
        "filename": "gemma-2-2b-it-q4_k_m.gguf",
        "url": "https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf",
        "size_gb": 1.5,
    },
    "phi-3.5-mini": {
        "name": "Phi-3.5-mini-instruct-Q4_K_M",
        "filename": "phi-3.5-mini-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf",
        "size_gb": 2.2,
    },
}

DEFAULT_MODEL = "gemma-2-2b"

# llama.cpp Android server binary
LLAMACPP_ANDROID_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/latest/download/llama-server-android-arm64.zip"
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def run(cmd: list[str] | str, check=True, capture=True, timeout=60) -> subprocess.CompletedProcess:
    """Run a shell command and return result."""
    if isinstance(cmd, str):
        cmd = cmd.split()
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=check,
        timeout=timeout,
    )


def adb(*args, check=True, timeout=30) -> subprocess.CompletedProcess:
    """Run an ADB command."""
    return run(["adb", *args], check=check, timeout=timeout)


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ─── Step 1: Check ADB ──────────────────────────────────────────────────────

def check_adb_installed():
    section("Step 1: Checking ADB")
    if not shutil.which("adb"):
        print("ERROR: adb not found in PATH.")
        print("Install with: sudo dnf install android-tools  (Fedora)")
        print("         or:  sudo apt install adb             (Debian/Ubuntu)")
        sys.exit(1)
    print("  [OK] adb found")


def check_device_connected():
    result = adb("devices", check=False)
    lines = [l for l in result.stdout.strip().splitlines()[1:] if l.strip()]
    authorized = [l for l in lines if "device" in l and "unauthorized" not in l]

    if not authorized:
        if any("unauthorized" in l for l in lines):
            print("ERROR: Device connected but not authorized.")
            print("  -> Check the phone for the USB debugging authorization prompt.")
        else:
            print("ERROR: No device connected.")
            print("  -> Connect your Samsung S24 FE via USB with USB Debugging enabled.")
        sys.exit(1)

    serial = authorized[0].split()[0]
    print(f"  [OK] Device connected: {serial}")
    return serial


def get_device_info():
    model = adb("shell", "getprop", "ro.product.model", check=False).stdout.strip()
    soc = adb("shell", "getprop", "ro.hardware.chipname", check=False).stdout.strip()
    android_ver = adb("shell", "getprop", "ro.build.version.release", check=False).stdout.strip()
    ram = adb("shell", "cat", "/proc/meminfo", check=False).stdout
    total_ram = "unknown"
    for line in ram.splitlines():
        if "MemTotal" in line:
            kb = int(re.search(r"(\d+)", line).group(1))
            total_ram = f"{kb / 1024 / 1024:.1f} GB"
            break

    print(f"  Model:   {model}")
    print(f"  SoC:     {soc}")
    print(f"  Android: {android_ver}")
    print(f"  RAM:     {total_ram}")
    return {"model": model, "soc": soc, "android": android_ver, "ram": total_ram}


# ─── Step 2: Download binaries ──────────────────────────────────────────────

def ensure_local_dir():
    local_dir = Path(__file__).parent / "assets"
    local_dir.mkdir(exist_ok=True)
    return local_dir


def download_file(url: str, dest: Path, desc: str):
    if dest.exists():
        print(f"  [SKIP] {desc} already downloaded: {dest.name}")
        return
    print(f"  Downloading {desc}...")
    print(f"    URL: {url}")
    print(f"    Dest: {dest}")
    try:
        urllib.request.urlretrieve(url, dest, reporthook=_progress)
        print()  # newline after progress
    except Exception as e:
        print(f"\n  ERROR downloading {desc}: {e}")
        print(f"  Please download manually from: {url}")
        print(f"  Place the file at: {dest}")
        sys.exit(1)


def _progress(count, block_size, total_size):
    if total_size > 0:
        pct = min(100, count * block_size * 100 // total_size)
        mb = count * block_size / 1024 / 1024
        total_mb = total_size / 1024 / 1024
        print(f"\r    {mb:.1f}/{total_mb:.1f} MB ({pct}%)", end="", flush=True)


def download_llamacpp_server(assets_dir: Path) -> Path:
    section("Step 2a: llama.cpp Android server")
    zip_path = assets_dir / "llama-server-android-arm64.zip"
    binary_path = assets_dir / "llama-server"

    if binary_path.exists():
        print(f"  [SKIP] Server binary already exists")
        return binary_path

    download_file(LLAMACPP_ANDROID_URL, zip_path, "llama.cpp Android server")

    print("  Extracting...")
    import zipfile
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Find the server binary inside the zip
        for name in zf.namelist():
            if "llama-server" in name and not name.endswith("/"):
                with zf.open(name) as src, open(binary_path, "wb") as dst:
                    dst.write(src.read())
                break
    binary_path.chmod(0o755)
    print(f"  [OK] Extracted: {binary_path}")
    return binary_path


def download_model(model_key: str, assets_dir: Path) -> Path:
    section("Step 2b: Model weights")
    model = MODELS[model_key]
    model_path = assets_dir / model["filename"]
    download_file(model["url"], model_path, f"{model['name']} (~{model['size_gb']} GB)")
    return model_path


# ─── Step 3: Push to device ─────────────────────────────────────────────────

def push_to_device(server_binary: Path, model_path: Path):
    section("Step 3: Pushing files to device")

    # Create directories on device
    adb("shell", "mkdir", "-p", DEVICE_MODEL_DIR)
    adb("shell", "mkdir", "-p", DEVICE_BIN_DIR)

    # Push server binary
    device_server = f"{DEVICE_BIN_DIR}/llama-server"
    print(f"  Pushing server binary...")
    adb("push", str(server_binary), device_server, timeout=120)
    adb("shell", "chmod", "755", device_server)
    print(f"  [OK] Server at {device_server}")

    # Push model
    device_model = f"{DEVICE_MODEL_DIR}/{model_path.name}"
    print(f"  Pushing model weights (this may take a few minutes)...")
    adb("push", str(model_path), device_model, timeout=600)
    print(f"  [OK] Model at {device_model}")

    return device_server, device_model


# ─── Step 4: Start inference server ─────────────────────────────────────────

def kill_existing_server():
    """Kill any existing llama-server process on the device."""
    result = adb("shell", "pidof", "llama-server", check=False)
    if result.stdout.strip():
        print(f"  Killing existing server (PID: {result.stdout.strip()})...")
        adb("shell", "kill", result.stdout.strip(), check=False)
        time.sleep(2)


def start_server(device_server: str, device_model: str, port: int):
    section("Step 4: Starting inference server on device")
    kill_existing_server()

    cmd = [
        "adb", "shell",
        f"nohup {device_server}"
        f" --model {device_model}"
        f" --host 0.0.0.0"
        f" --port {port}"
        f" --n-gpu-layers 99"   # offload to GPU/NPU
        f" --ctx-size 2048"
        f" --threads 4"         # Exynos 2400e has 8 cores, use 4
        f" > /data/local/tmp/llama-server.log 2>&1 &"
    ]
    print(f"  Starting llama-server on device port {port}...")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)

    # Verify server started
    result = adb("shell", "pidof", "llama-server", check=False)
    if not result.stdout.strip():
        print("  ERROR: Server failed to start. Checking logs...")
        log = adb("shell", "cat", "/data/local/tmp/llama-server.log", check=False)
        print(log.stdout[-500:] if log.stdout else "  (no log output)")
        sys.exit(1)

    pid = result.stdout.strip()
    print(f"  [OK] Server running (PID: {pid})")
    return pid


# ─── Step 5: Port forwarding ────────────────────────────────────────────────

def setup_port_forward(port: int):
    section("Step 5: ADB port forwarding")
    adb("forward", f"tcp:{port}", f"tcp:{port}")
    print(f"  [OK] localhost:{port} -> device:{port}")


# ─── Step 6: Verify & benchmark ─────────────────────────────────────────────

def wait_for_server(port: int, retries=15, delay=2):
    section("Step 6: Verifying endpoint")
    url = f"http://localhost:{port}/health"
    for i in range(retries):
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            if resp.status == 200:
                print(f"  [OK] Server healthy after {(i+1)*delay}s")
                return True
        except Exception:
            pass
        print(f"  Waiting for server... ({i+1}/{retries})")
        time.sleep(delay)

    print("  ERROR: Server did not become healthy.")
    print("  Check device logs: adb shell cat /data/local/tmp/llama-server.log")
    return False


def benchmark(port: int):
    section("Benchmark: Quick inference test")
    url = f"http://localhost:{port}/v1/chat/completions"
    payload = json.dumps({
        "model": "local",
        "messages": [{"role": "user", "content": "What is 2+2? Answer in one word."}],
        "max_tokens": 32,
        "temperature": 0.1,
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode())
        elapsed = time.time() - start

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        tps = completion_tokens / elapsed if elapsed > 0 else 0

        print(f"  Response: {content.strip()}")
        print(f"  Tokens:   {completion_tokens}")
        print(f"  Time:     {elapsed:.2f}s")
        print(f"  Speed:    {tps:.1f} tokens/sec")
        return {"tps": tps, "latency": elapsed}
    except Exception as e:
        print(f"  Benchmark failed: {e}")
        return None


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Deploy LLM on Android via ADB")
    parser.add_argument("--model", choices=list(MODELS.keys()), default=DEFAULT_MODEL,
                        help=f"Model to deploy (default: {DEFAULT_MODEL})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Port for the API endpoint (default: {DEFAULT_PORT})")
    parser.add_argument("--skip-push", action="store_true",
                        help="Skip downloading & pushing (files already on device)")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip downloading (files already in ./assets)")
    parser.add_argument("--lan", action="store_true",
                        help="Also expose endpoint to LAN via socat")
    args = parser.parse_args()

    print("""
    ╔══════════════════════════════════════════════╗
    ║   Android Local LLM Deployer                 ║
    ║   Samsung S24 FE (Exynos 2400e)              ║
    ╚══════════════════════════════════════════════╝
    """)

    # Step 1: ADB
    check_adb_installed()
    serial = check_device_connected()
    info = get_device_info()

    assets_dir = ensure_local_dir()

    if not args.skip_push:
        if not args.skip_download:
            # Step 2: Download
            server_binary = download_llamacpp_server(assets_dir)
            model_path = download_model(args.model, assets_dir)
        else:
            server_binary = assets_dir / "llama-server"
            model_path = assets_dir / MODELS[args.model]["filename"]
            if not server_binary.exists() or not model_path.exists():
                print("ERROR: --skip-download but files missing in ./assets/")
                sys.exit(1)

        # Step 3: Push
        device_server, device_model = push_to_device(server_binary, model_path)
    else:
        device_server = f"{DEVICE_BIN_DIR}/llama-server"
        device_model = f"{DEVICE_MODEL_DIR}/{MODELS[args.model]['filename']}"

    # Step 4: Start
    pid = start_server(device_server, device_model, args.port)

    # Step 5: Forward
    setup_port_forward(args.port)

    # Step 6: Verify
    if wait_for_server(args.port):
        metrics = benchmark(args.port)

        # LAN exposure via socat (optional)
        lan_info = ""
        if args.lan:
            if shutil.which("socat"):
                lan_ip = _get_lan_ip()
                subprocess.Popen(
                    ["socat", f"TCP-LISTEN:8080,fork,reuseaddr", f"TCP:localhost:{args.port}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                lan_info = f"\n  LAN endpoint:   http://{lan_ip}:{args.port}/v1/chat/completions"
            else:
                lan_info = "\n  (socat not installed — skipping LAN exposure)"

        section("READY")
        print(f"""
  Endpoint:       http://localhost:{args.port}/v1/chat/completions
  Model:          {MODELS[args.model]['name']}{lan_info}
  Device:         {info['model']} ({info['soc']})
  Server PID:     {pid}

  Test with curl:
    curl http://localhost:{args.port}/v1/chat/completions \\
      -H "Content-Type: application/json" \\
      -d '{{"model":"local","messages":[{{"role":"user","content":"Hello!"}}]}}'

  Stop server:
    adb shell kill {pid}
    adb forward --remove tcp:{args.port}
""")
    else:
        print("\n  Server failed to start. Check logs on device.")
        sys.exit(1)


def _get_lan_ip():
    """Get the machine's LAN IP."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "0.0.0.0"
    finally:
        s.close()


if __name__ == "__main__":
    main()
