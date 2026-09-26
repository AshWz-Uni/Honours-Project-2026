import json
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "llm_config.json"

with CONFIG_PATH.open("r", encoding="utf-8") as file:
    config = json.load(file)

MODEL = config["model"]
BASE_URL = config["base_url"].rstrip("/")
DEFAULT_TEMPERATURE = config.get("temperature", 0.25)
TIMEOUT = config.get("timeout", 120)
SEED = config.get("seed")  # optional: fixed seed makes evaluation runs repeatable


def ask_llm(prompt: str, temperature: float | None = None, json_mode: bool = False) -> str:
    """Call Ollama and return only the generated text.

    ``json_mode=True`` asks Ollama to constrain the output to valid JSON, which
    makes the private diagnostic pass far more reliable on a 7B model.
    """
    options = {
        "temperature": DEFAULT_TEMPERATURE if temperature is None else temperature,
        "num_predict": config.get("max_tokens", 2048),
    }
    if SEED is not None:
        options["seed"] = SEED

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": options,
    }
    if json_mode:
        payload["format"] = "json"

    response = requests.post(f"{BASE_URL}/api/generate", json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()

    if "response" not in data:
        raise RuntimeError("Ollama response did not contain a 'response' field")

    return data["response"].strip()
