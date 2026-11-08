"""Persist local model preferences without writing credentials or global settings."""
import json
import os
from pathlib import Path

from .ollama import Ollama

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "storage" / "settings.json"
DEFAULTS = {"answer_mode": "ollama", "chat_model": "qwen3:4b", "embedding_model": "",
            "ollama_url": "http://127.0.0.1:11434"}


def load_settings(path=SETTINGS_PATH):
    settings = dict(DEFAULTS)
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        settings.update({key: value for key, value in saved.items() if key in DEFAULTS and isinstance(value, str)})
        Ollama(settings["ollama_url"])  # Reject a persisted remote endpoint.
    except (OSError, ValueError, AttributeError):
        settings = dict(DEFAULTS)
    if os.environ.get("RAGBOT_ANSWER_MODE") in ("evidence", "ollama"):
        settings["answer_mode"] = os.environ["RAGBOT_ANSWER_MODE"]
    return settings


def save_settings(settings, path=SETTINGS_PATH):
    Ollama(settings["ollama_url"])
    if settings["answer_mode"] not in ("evidence", "ollama") or "cloud" in settings["chat_model"].lower():
        raise ValueError("Choose a local model and a supported answer mode.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({key: settings[key] for key in DEFAULTS}, indent=2), encoding="utf-8")
    temporary.replace(path)
