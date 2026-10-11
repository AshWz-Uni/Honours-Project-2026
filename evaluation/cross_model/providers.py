"""Local Ollama and dry-run chat adapters for the cross-model study.

Every adapter takes the SAME inputs (a system prompt, a list of
``{"role": "user"|"assistant", "content": str}`` messages and the shared
sampling settings) and returns a ``ChatResult``. Nothing here knows about
tutoring; keeping it that way is what makes the comparison fair.

ChatGPT and Claude are deliberately not called through APIs. Their web-app responses are captured using the manual export/import workflow.

The existing ``backend/services/llm_service.py`` is NOT used or modified: it is
single-prompt/``/api/generate`` based, whereas a fair comparison needs the chat
message format that ChatGPT and Claude are designed for.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import requests

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
MAX_ATTEMPTS = 5


@dataclass
class ChatResult:
    text: str
    model_returned: str = ""
    finish_reason: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_s: float = 0.0
    params_sent: dict = field(default_factory=dict)


class ProviderError(RuntimeError):
    pass


def _post_with_retry(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    """POST JSON, retrying transient failures with exponential backoff."""
    last = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last = f"{type(exc).__name__}: {exc}"
        else:
            if response.status_code == 200:
                return response.json()
            last = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code not in RETRY_STATUS:
                break  # e.g. 400/401/404: retrying will not help
        if attempt < MAX_ATTEMPTS:
            time.sleep(min(2 ** attempt, 30))
    raise ProviderError(f"{url} failed after retries. Last error: {last}")


def _api_key(cfg: dict) -> str:
    env = cfg["api_key_env"]
    key = os.environ.get(env, "").strip()
    if not key:
        raise ProviderError(
            f"Environment variable {env} is not set. Put it in a .env file in the project root "
            f"(already git-ignored) or export it in your shell."
        )
    return key


# --------------------------------------------------------------------------- #
# Ollama (Code Llama)
# --------------------------------------------------------------------------- #
def ollama_chat(cfg: dict, system: str, messages: list[dict], sampling: dict, seed: int | None) -> ChatResult:
    # The controlled prompt is ~2k tokens and the full conversation can reach ~3k, which is more than
    # Ollama's default context window. Beyond the window Ollama silently drops the START of the prompt
    # (i.e. the system prompt), so the window is always set explicitly and checked below.
    num_ctx = int(cfg.get("num_ctx", 8192))
    options = {"temperature": sampling["temperature"], "num_predict": sampling["max_tokens"], "num_ctx": num_ctx}
    if seed is not None:
        options["seed"] = seed
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": system}, *messages],
        "stream": False,
        "options": options,
    }
    started = time.time()
    data = _post_with_retry(f"{cfg['base_url'].rstrip('/')}/api/chat", {}, payload, cfg.get("timeout", 120))
    text = (data.get("message") or {}).get("content")
    if text is None:
        raise ProviderError("Ollama response had no message.content")
    prompt_tokens = data.get("prompt_eval_count")
    if prompt_tokens is not None and prompt_tokens + sampling["max_tokens"] > num_ctx:
        raise ProviderError(
            f"Prompt used {prompt_tokens} tokens of a {num_ctx}-token context window, so Ollama may have truncated "
            f"the system prompt. Raise num_ctx for the codellama_prompt condition in experiment_config.json."
        )
    return ChatResult(
        text=text.strip(),
        model_returned=data.get("model", cfg["model"]),
        finish_reason=data.get("done_reason", ""),
        input_tokens=data.get("prompt_eval_count"),
        output_tokens=data.get("eval_count"),
        latency_s=round(time.time() - started, 3),
        params_sent={"temperature": options["temperature"], "num_predict": options["num_predict"],
                     "num_ctx": num_ctx, "seed": seed},
    )


# --------------------------------------------------------------------------- #
# Mock (dry runs only - never a result)
# --------------------------------------------------------------------------- #
_MOCK_QUESTIONS = (
    "Which input would you trace first to confirm that?",
    "What does the function return for a small example, step by step?",
    "How would you check that idea on the example in the problem statement?",
    "Why does the earlier failing case now behave the way you expect?",
    "Which unusual input would you try next, and what should come back?",
)


def mock_chat(cfg: dict, system: str, messages: list[dict], sampling: dict, seed: int | None) -> ChatResult:
    turn = sum(1 for m in messages if m["role"] == "user")
    if turn >= 6:
        text = "You found the cause, proposed a change yourself and checked it. Run it once more on the original example and an edge case."
    else:
        text = _MOCK_QUESTIONS[(turn - 1) % len(_MOCK_QUESTIONS)]
    return ChatResult(text=text, model_returned="mock", finish_reason="stop", input_tokens=0, output_tokens=0)


PROVIDERS = {
    "ollama": ollama_chat,
    "mock": mock_chat,
}


def chat(cfg: dict, system: str, messages: list[dict], sampling: dict, seed: int | None) -> ChatResult:
    try:
        fn = PROVIDERS[cfg["provider"]]
    except KeyError:
        raise ProviderError(f"Unknown provider {cfg.get('provider')!r}; expected one of {sorted(PROVIDERS)}") from None
    return fn(cfg, system, messages, sampling, seed)
