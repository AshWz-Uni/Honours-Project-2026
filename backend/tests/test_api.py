"""API-level tests: conversation state must persist across requests."""

import pytest
from fastapi.testclient import TestClient

from backend.agent import tutor_agent as ta
from backend.main import app

client = TestClient(app)

CODE = "def f(a):\n    return a"
DIAG = '{"problem_identified": %s, "solution_proposed": false, "solution_correct": false, "solution_validated": false, "student_evidence": "", "next_step": "diagnose"}'


@pytest.fixture
def fake_llm(monkeypatch):
    def fake(prompt, *args, **kwargs):
        if "private diagnostic component" in prompt.lower():
            return DIAG % "false"
        return f"Which value does a hold at step {len(prompt) % 89}?"

    monkeypatch.setattr(ta, "ask_llm", fake)


def test_conversation_id_is_returned_and_state_persists(fake_llm):
    first = client.post("/chat", json={"code": CODE, "question": "It is wrong", "problem": "Return a."}).json()
    cid = first["conversation_id"]
    second = client.post("/chat", json={"code": CODE, "question": "Still wrong", "conversation_id": cid}).json()
    assert second["conversation_id"] == cid  # same conversation, not a new one
    assert first["stage"] == "clarify" and second["stage"] == "predict"  # progressed


def test_state_endpoint_is_closed_unless_debug(fake_llm, monkeypatch):
    cid = client.post("/chat", json={"code": CODE, "question": "It is wrong"}).json()["conversation_id"]
    monkeypatch.delenv("TUTOR_DEBUG", raising=False)
    assert client.get(f"/chat/{cid}/state").status_code == 404
    monkeypatch.setenv("TUTOR_DEBUG", "1")
    state = client.get(f"/chat/{cid}/state").json()
    assert state["question_count"] == 1 and state["concluded"] is False


def test_delete_clears_conversation(fake_llm):
    cid = client.post("/chat", json={"code": CODE, "question": "It is wrong"}).json()["conversation_id"]
    assert client.delete(f"/chat/{cid}").status_code == 200
    assert client.delete(f"/chat/{cid}").status_code == 404
