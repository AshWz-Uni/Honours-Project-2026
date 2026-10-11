"""Tests for the cross-model evaluation tooling.

These check the EXPERIMENT'S CONTROLS (same prompt, same turns, same sampling
for every model; no label leakage into the blind set) and the plumbing. They say
nothing about how well any model tutors.
"""

import csv
import json

import pytest

from backend.agent import tutor_agent as ta
from backend.agent.prompts import (
    CONCLUSION_PROMPT,
    CONSOLIDATION_FOCI,
    LANGUAGE_NOTES,
    STAGE_GUIDANCE,
    SYSTEM_PROMPT,
)
from dataset.leetcode_eval import get_problems
from evaluation.cross_model import blind_rating as br
from evaluation.cross_model import controlled_prompt as cp
from evaluation.cross_model import metrics as mx
from evaluation.cross_model import providers
from evaluation.cross_model import run_cross_model_eval as runner
from evaluation.run_leetcode_eval import scripted_turns

PY = get_problems("python")
JS = get_problems("javascript")


# --------------------------------------------------------------------------- #
# Frozen prompt: it must still be the project's own pedagogy
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("language", cp.LANGUAGES)
def test_prompt_embeds_the_projects_own_rules_verbatim(language):
    """If this fails, backend/agent/prompts.py changed; keep the controlled prompt identifier stable."""
    prompt = cp.build_system_prompt(language)
    assert SYSTEM_PROMPT in prompt
    for stage in ("clarify", "predict", "trace", "diagnose", "propose", "test", "validate"):
        assert STAGE_GUIDANCE[stage] in prompt, stage
    # consolidate is reworded on purpose: the agent injects ONE focus per turn, the prompt must list all four
    assert STAGE_GUIDANCE["consolidate"].split("this focus")[0].strip() in prompt
    for focus in CONSOLIDATION_FOCI:
        assert (focus[0].upper() + focus[1:] + ".") in prompt
    for line in CONCLUSION_PROMPT.split("Rules:", 1)[1].strip().splitlines():
        assert line.strip() in prompt


def test_language_notes_match_the_backend():
    assert json.loads(cp._NOTES_FILE.read_text(encoding="utf-8")) == dict(LANGUAGE_NOTES)
    assert LANGUAGE_NOTES["javascript"].strip() in cp.build_system_prompt("javascript")
    py = cp.build_system_prompt("python")
    assert "LANGUAGE:" not in py and "{{" not in py


def test_conclusion_rule_matches_the_agents_threshold_and_script_length():
    assert f"at least {ta.MIN_SOCRATIC_QUESTIONS} Socratic questions" in cp.build_system_prompt("python")
    assert mx.EXPECTED_CONCLUSION_TURN == ta.MIN_SOCRATIC_QUESTIONS + 1
    for problem in (*PY, *JS):
        assert len(scripted_turns(problem)) == runner.EXPECTED_TURNS == mx.EXPECTED_CONCLUSION_TURN


def test_prompt_is_stable_and_line_ending_insensitive():
    assert cp.build_system_prompt("python") == cp.build_system_prompt("python")
    assert cp.prompt_sha256("python") != cp.prompt_sha256("javascript")
    assert cp._normalise("a\r\nb\rc") == "a\nb\nc"


def test_unknown_language_rejected():
    with pytest.raises(ValueError):
        cp.build_system_prompt("ruby")


# --------------------------------------------------------------------------- #
# Message layout
# --------------------------------------------------------------------------- #
def test_first_message_has_problem_code_and_student_text_in_order():
    p = PY[0]
    msg = cp.build_first_user_message(p["code"], p["problem"], "my message", "python")
    assert msg.index("Problem statement:") < msg.index("```python") < msg.index("Student message:")
    assert p["code"] in msg and p["problem"] in msg and msg.endswith("my message")
    assert "```javascript" in cp.build_first_user_message("x", "y", "z", "javascript")


def test_build_messages_alternates_and_only_first_turn_carries_code():
    p = PY[0]
    turns = [t for _, t in scripted_turns(p)]
    replies = [f"reply {i}?" for i in range(3)]
    msgs = cp.build_messages(p, turns[:4], replies)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant", "user", "assistant", "user"]
    assert p["code"] in msgs[0]["content"]
    assert msgs[2]["content"] == turns[1] and msgs[6]["content"] == turns[3]
    assert all(p["code"] not in m["content"] for m in msgs[1:])
    with pytest.raises(ValueError):
        cp.build_messages(p, turns[:3], replies)


def test_manual_first_message_wraps_the_same_prompt():
    p = JS[2]
    text = cp.manual_first_message(p, "hello")
    assert cp.build_system_prompt("javascript") in text
    assert cp.build_first_user_message(p["code"], p["problem"], "hello", "javascript") in text




# --------------------------------------------------------------------------- #
# Manual web-app evaluation (no external model API calls)
# --------------------------------------------------------------------------- #
def test_manual_sheet_round_trip(tmp_path):
    problem = PY[0]
    sheet = runner.render_manual_sheet(problem, "chatgpt")
    filled = sheet.replace("<!-- paste the model's reply here -->", "A tutor response.")
    info, replies = runner.parse_manual_sheet(filled)
    assert info["condition"] == "chatgpt"
    assert info["language"] == "python"
    assert len(replies) == 1
    assert len(replies[0]) == runner.EXPECTED_TURNS
    assert info["repeat"] == 1


def test_export_creates_three_separate_files_per_problem(tmp_path):
    import argparse

    args = argparse.Namespace(condition="chatgpt", language="python", only="1", repeats=3, out=str(tmp_path))
    runner.cmd_export_manual(args)
    files = sorted((tmp_path / "chatgpt").glob("*.md"))
    assert [p.name for p in files] == [
        "python_01_two-sum_run1.md", "python_01_two-sum_run2.md", "python_01_two-sum_run3.md"
    ]
    for repeat, path in enumerate(files, start=1):
        text = path.read_text(encoding="utf-8")
        assert f"repeat={repeat} -->" in text.splitlines()[0]
        assert "# RUN 2" not in text
        assert len(list(__import__("re").finditer(r"^### TURN \d+ REPLY$", text, __import__("re").M))) == runner.EXPECTED_TURNS
        info, replies = runner.parse_manual_sheet(text.replace("<!-- paste the model's reply here -->", "A tutor response."))
        assert info["repeat"] == repeat
        assert len(replies) == 1


def test_provider_registry_has_no_paid_api_adapters():
    assert set(providers.PROVIDERS) == {"ollama", "mock"}
