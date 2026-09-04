from backend.agent import tutor_agent
from backend.agent.conversation import get_conversation


def test_solution_leak_detection():
    assert tutor_agent._contains_solution_leak("The answer is to change line 4.")
    assert tutor_agent._contains_solution_leak("You should replace x with y.")
    assert not tutor_agent._contains_solution_leak("What value does x have here?")


def test_tutor_returns_only_a_question_and_advances_stage(monkeypatch):
    outputs = iter([
        "likely_issue: condition\nnext_step: trace the condition",
        "What value does the condition evaluate with on the first iteration?",
    ])
    monkeypatch.setattr(tutor_agent, "ask_llm", lambda *args, **kwargs: next(outputs))

    response, conversation_id = tutor_agent.generate_tutor_response(
        code="for i in range(3):\n    print(i)",
        question="Why does this behave differently than I expected?",
    )

    conversation = get_conversation(conversation_id)
    assert response.endswith("?")
    assert "answer" not in response.lower()
    assert conversation is not None
    assert conversation.stage == 1
    assert len(conversation.messages) == 2


def test_leaking_generation_falls_back_to_safe_question(monkeypatch):
    outputs = iter([
        "diagnostic notes",
        "The answer is to change line 4.",
        "Replace the loop with this:\n```python\nprint('x')\n```",
    ])
    monkeypatch.setattr(tutor_agent, "ask_llm", lambda *args, **kwargs: next(outputs))

    response, _ = tutor_agent.generate_tutor_response(
        code="print('x')",
        question="Can you fix this?",
    )

    assert response.endswith("?")
    assert "answer is" not in response.lower()
    assert "```" not in response
