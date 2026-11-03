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


# --------------------------------------------------------------------------- #
# Tolerant reading of recorded worksheets (fenced replies, audit, exclusion)
# --------------------------------------------------------------------------- #
def _filled_sheet(replies, problem=None, condition="chatgpt", repeat=1, fenced=True):
    """A worksheet whose replies are wrapped in ````text fences, as in the recorded manual_pack."""
    sheet = runner.render_manual_sheet(problem or PY[0], condition, repeat)
    head, _ = sheet.split("## RECORD REPLIES")
    body = ["## RECORD REPLIES", ""]
    for i, reply in enumerate(replies, start=1):
        body += [f"### TURN {i} REPLY", "````text" if fenced else "", reply, "````" if fenced else "", ""]
    return head + "\n".join(body)


def test_unwrap_reply_strips_only_the_recording_wrapper():
    assert runner.unwrap_reply("````text\nWhat happens for [3, 3]?\n````") == "What happens for [3, 3]?"
    assert runner.unwrap_reply("```text\nHello?\n```") == "Hello?"
    assert runner.unwrap_reply("<!-- paste the model's reply here -->\nPlain reply?") == "Plain reply?"
    # a real code block in the reply must survive so the code-block metric can see it
    assert runner.unwrap_reply("```python\nreturn [i, j]\n```") == "```python\nreturn [i, j]\n```"
    inner = "Try this:\n```python\nx = 1\n```\nWhy?"
    assert runner.unwrap_reply(f"````text\n{inner}\n````") == inner


def test_fenced_worksheet_parses_to_clean_replies():
    replies = [f"Question number {i}?" for i in range(1, 6)] + ["Well done; run it on an edge case."]
    info, parsed = runner.parse_manual_sheet(_filled_sheet(replies))
    assert parsed[0] == replies
    assert mx.turn_metrics(parsed[0][0], 1, PY[0], ["x"], [])["has_code_block"] == 0


def test_parser_tolerates_heading_variants_but_rejects_duplicates():
    replies = [f"Reply {i}?" for i in range(1, 7)]
    sheet = _filled_sheet(replies).replace("### TURN 2 REPLY", "## Turn 2 reply:")
    assert runner.parse_manual_sheet(sheet)[1][0] == replies
    with pytest.raises(ValueError, match="more than once"):
        runner.parse_manual_sheet(_filled_sheet(replies) + "\n### TURN 3 REPLY\nagain\n")


def test_audit_flags_student_text_pasted_as_reply():
    scripted = [t for _, t in scripted_turns(PY[0])]
    good = [f"Different tutor question {i}, about something else entirely?" for i in range(1, 7)]
    assert runner.audit_replies(good, scripted) == []
    bad = list(good)
    bad[3] = scripted[3]                        # the student's line pasted into the reply box
    assert ("ERROR", "turn 4: reply is (almost) identical to the scripted STUDENT message - wrong box?") in runner.audit_replies(bad, scripted)
    assert any(lvl == "ERROR" and "identical replies" in m for lvl, m in runner.audit_replies([good[0]] * 6, scripted))


def test_load_manual_records_excludes_recording_errors(tmp_path):
    scripted = [t for _, t in scripted_turns(PY[0])]
    ok = [f"Tutor question {i} about the loop bounds on line {i}?" for i in range(1, 7)]
    (tmp_path / "python_01_two-sum_run1.md").write_text(_filled_sheet(ok, repeat=1), encoding="utf-8")
    (tmp_path / "python_01_two-sum_run2.md").write_text(_filled_sheet(scripted, repeat=2), encoding="utf-8")
    recs, failures, audit = runner.load_manual_records(tmp_path, "chatgpt", "m", "t")
    assert [r["repeat"] for r in recs] == [1]
    assert any("EXCLUDED" in f for f in failures) and any(a.startswith("ERROR") for a in audit)
    recs_all, _, _ = runner.load_manual_records(tmp_path, "chatgpt", "m", "t", keep_invalid=True)
    assert len(recs_all) == 2
