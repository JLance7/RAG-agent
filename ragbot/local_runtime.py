"""Project-local Ollama setup/start helper. Downloads occur ONLY in setup mode.

The runtime release is pinned and SHA-256 verified. No global PATH, installer,
registry entry, startup task, or model-service registration is created.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

import requests

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.40.15"
URL = f"https://github.com/ollama/ollama/releases/download/v{VERSION}/ollama-windows-amd64.zip"
SHA256 = "9ca74a7ab66ec86870b1eecac7df160df08dc4e3a291ab5d2d59bcf9310221c6"
DEFAULT_MODEL = "qwen3:4b"
ENDPOINT = "http://127.0.0.1:11434"


def local_session():
    session = requests.Session()
    session.trust_env = False
    return session


def ready():
    try:
        with local_session() as session:
            response = session.get(ENDPOINT + "/api/version", timeout=(1, 2), allow_redirects=False)
            return response.status_code == 200 and bool(response.json().get("version"))
    except (requests.RequestException, ValueError):
        return False


def install():
    runtime = ROOT / ".runtime" / "ollama"
    stamp = runtime / "installed.json"
    if stamp.exists() and (runtime / "ollama.exe").exists():
        if json.loads(stamp.read_text())["version"] == VERSION:
            print(f"Ollama {VERSION} runtime is already installed.", flush=True)
            return
    if os.name != "nt":
        raise RuntimeError("The bundled runtime helper targets Windows. Install Ollama for your OS separately.")
    runtime.mkdir(parents=True, exist_ok=True)
    archive_path = runtime.parent / "ollama-download.zip"
    print("Downloading the official Ollama Windows runtime (~1.5 GB)...", flush=True)
    digest, received, next_report = hashlib.sha256(), 0, 0
    # Downloading runtime/model weights is allowed here, but no documents are
    # included in these requests. Generation uses the loopback adapter only.
    with requests.get(URL, stream=True, timeout=(10, 120)) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", 0))
        with archive_path.open("wb") as output:
            for block in response.iter_content(1024 * 1024):
                output.write(block)
                digest.update(block)
                received += len(block)
                if received >= next_report:
                    print(f"Runtime download: {received // (1024 * 1024)} MB" + (f" / {total // (1024 * 1024)} MB" if total else ""), flush=True)
                    next_report = received + 128 * 1024 * 1024
    if digest.hexdigest() != SHA256:
        raise RuntimeError("Ollama archive checksum did not match the official release digest; nothing was executed.")
    print("Runtime checksum verified. Extracting...", flush=True)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            destination = (runtime / member.filename).resolve()
            if not destination.is_relative_to(runtime.resolve()):
                raise RuntimeError("Unexpected archive path.")
        archive.extractall(runtime)
    if not (runtime / "ollama.exe").exists():
        raise RuntimeError("Ollama executable missing from the downloaded package.")
    stamp.write_text(json.dumps({"version": VERSION, "url": URL, "sha256": SHA256}, indent=2))
    archive_path.unlink()  # Only our verified download file, not user data.


def start():
    if ready():
        return False
    executable = ROOT / ".runtime" / "ollama" / "ollama.exe"
    if not executable.exists():
        raise RuntimeError("Local Ollama runtime is not installed. Run Setup Local Model.bat first.")
    storage = ROOT / "storage"
    storage.mkdir(exist_ok=True)
    environment = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_MODELS": str(storage / "ollama-models"),
                   "OLLAMA_NO_CLOUD": "1", "OLLAMA_KEEP_ALIVE": "10m", "OLLAMA_CONTEXT_LENGTH": "8192"}
    with (storage / "ollama-server.log").open("ab") as output:
        process = subprocess.Popen([str(executable), "serve"], cwd=ROOT, env=environment,
                                   stdout=output, stderr=output, stdin=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(60):
        if ready():
            (storage / "ollama-process.json").write_text(json.dumps({"pid": process.pid, "executable": str(executable), "cloud_disabled": True}))
            return True
        if process.poll() is not None:
            raise RuntimeError("Ollama exited. Check storage/ollama-server.log.")
        time.sleep(.5)
    raise RuntimeError("Ollama did not become ready. Check storage/ollama-server.log.")


def pull_model(model):
    if "cloud" in model.lower() or not model.strip():
        raise ValueError("Choose a local model tag, not a cloud model.")
    with local_session() as session:
        tags = session.get(ENDPOINT + "/api/tags", timeout=(3, 10)).json()
        if model in [entry["name"] for entry in tags.get("models", [])]:
            print(f"Model {model} is already installed.", flush=True)
            return
        print(f"Downloading local model {model} (~2.5 GB for qwen3:4b)...", flush=True)
        with session.post(ENDPOINT + "/api/pull", json={"model": model, "stream": True}, timeout=(5, 180), allow_redirects=False) as response:
            response.raise_for_status()
            last = 0
            for line in response.iter_lines():
                if not line:
                    continue
                update = json.loads(line)
                if update.get("error"):
                    raise RuntimeError(update["error"])
                if time.monotonic() - last > 5 or update.get("status") == "success":
                    completed, total = update.get("completed", 0), update.get("total", 0)
                    print(update.get("status", "Downloading") + (f" · {completed / total * 100:.0f}%" if total else ""), flush=True)
                    last = time.monotonic()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "start", "status"])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    if args.command == "setup":
        install()
        start()
        pull_model(args.model)
        print("Ollama and the local model are ready.", flush=True)
    elif args.command == "start":
        start()
        print("Local Ollama server is ready.", flush=True)
    else:
        print("Ready" if ready() else "Not running")


if __name__ == "__main__":
    main()
