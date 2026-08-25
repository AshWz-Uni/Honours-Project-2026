import json
import requests

CONFIG_PATH = "config/llm_config.json"

with open(CONFIG_PATH, "r") as file:
    config = json.load(file)

MODEL = config["model"]
BASE_URL = config["base_url"]
TEMPERATURE = config["temperature"]

def ask_llm(prompt: str):

    response = requests.post(
        f"{BASE_URL}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": TEMPERATURE
            }
        }
    )

    data = response.json()

    return data["response"]
