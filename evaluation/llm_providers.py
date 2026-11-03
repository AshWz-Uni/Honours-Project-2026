"""Provider adapters for the controlled LLM comparison.

The evaluation harness treats each provider as a conversational tutor and measures
the wall-clock time for each completed response. API credentials are read from
environment variables; they are never stored in the project.

Providers:
- codellama: the project's local Ollama/Code Llama agent.
- chatgpt: OpenAI Responses API (the API-backed ChatGPT comparison).
- claude: Anthropic Messages API.

However, this module is no longer effective due to cost limitations regarding the 
ChatGPT and Claude APIs. Instead, their web application versions will be substituted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from dotenv import load_dotenv

load_dotenv()

print("OpenAI:", bool(os.getenv("OPENAI_API_KEY")))
print("Anthropic:", bool(os.getenv("ANTHROPIC_API_KEY")))

@dataclass
class ProviderReply:
    text: str
    model: str


class ProviderError(RuntimeError):
    pass


class ExternalProvider:
    name: str
    model: str

    def reply(self, prompt: str, history: list[dict[str, str]]) -> ProviderReply:
        raise NotImplementedError

    def reset(self) -> None:
        """Start a fresh provider conversation for the next benchmark problem."""
        return None

    def close(self) -> None:
        """Release provider state, if any."""
        return None


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ProviderError(f"Missing required environment variable: {name}")
    return value


def _extract_openai_text(data: dict[str, Any]) -> str:
    # Responses API convenience field, when present.
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()

    chunks: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") in {"output_text", "text"} and isinstance(value.get("text"), str):
                chunks.append(value["text"])
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data.get("output", data))
    text = "\n".join(c.strip() for c in chunks if c.strip()).strip()
    if not text:
        raise ProviderError("OpenAI response did not contain text output")
    return text


class ChatGPTProvider(ExternalProvider):
    name = "chatgpt"

    def __init__(self) -> None:
        self.api_key = _require_env("OPENAI_API_KEY")
        self.model = _require_env("CHATGPT_MODEL")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.timeout = float(os.getenv("OPENAI_TIMEOUT", "180"))

    def reply(self, prompt: str, history: list[dict[str, str]]) -> ProviderReply:
        # The evaluation prompt already contains the full conversation. Sending
        # it as one user input makes the comparison deterministic at the harness
        # level and avoids provider-specific conversation storage.
        response = requests.post(
            f"{self.base_url}/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": [{"role": "user", "content": prompt}],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return ProviderReply(_extract_openai_text(response.json()), self.model)


class ClaudeProvider(ExternalProvider):
    name = "claude"

    def __init__(self) -> None:
        self.api_key = _require_env("ANTHROPIC_API_KEY")
        self.model = _require_env("CLAUDE_MODEL")
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        self.timeout = float(os.getenv("ANTHROPIC_TIMEOUT", "180"))

    def reply(self, prompt: str, history: list[dict[str, str]]) -> ProviderReply:
        response = requests.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": int(os.getenv("CLAUDE_MAX_TOKENS", "500")),
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        chunks = [
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        text = "\n".join(x.strip() for x in chunks if x.strip()).strip()
        if not text:
            raise ProviderError("Anthropic response did not contain text output")
        return ProviderReply(text, self.model)


def build_provider(name: str) -> ExternalProvider:
    name = name.lower()
    if name == "chatgpt":
        return ChatGPTProvider()
    if name == "claude":
        return ClaudeProvider()
    raise ProviderError(f"Unknown external provider: {name}")
