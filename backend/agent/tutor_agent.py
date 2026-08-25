from backend.services.llm_service import ask_llm
from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.conversation import (
    add_message,
    get_history
)

def generate_tutor_response(code: str, question: str):

    add_message(
        "student",
        f"Code:\n{code}\n\nQuestion:\n{question}"
    )

    history = get_history()

    conversation_text = ""

    for msg in history:

        role = msg["role"]

        if role == "student":
            conversation_text += f"Student:\n{msg['content']}\n\n"

        elif role == "assistant":
            conversation_text += f"Tutor:\n{msg['content']}\n\n"

    prompt = f"""
{SYSTEM_PROMPT}

Conversation History:

{conversation_text}

Respond as the tutor only.
"""

    response = ask_llm(prompt)

    add_message("assistant", response)

    return response
