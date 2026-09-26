import os
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from backend.agent.conversation import clear_conversation, get_conversation
from backend.agent.tutor_agent import generate_tutor_response, learning_state
from backend.api.models import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        response, conversation_id = generate_tutor_response(
            code=request.code,
            question=request.question,
            conversation_id=request.conversation_id,
            problem=request.problem,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Tutor model error: {exc}") from exc

    conversation = get_conversation(conversation_id)
    return ChatResponse(
        response=response,
        conversation_id=conversation_id,
        stage=conversation.stage_name if conversation else None,
        concluded=bool(conversation and conversation.concluded),
    )


@router.delete("/chat/{conversation_id}")
def clear_chat(conversation_id: str):
    if not clear_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"message": "Conversation cleared"}


@router.get("/chat/{conversation_id}/state")
def chat_state(conversation_id: str):
    """Learning-state snapshot for evaluation runs. Disabled unless TUTOR_DEBUG=1."""
    if os.getenv("TUTOR_DEBUG") != "1":
        raise HTTPException(status_code=404, detail="Not found")

    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        **learning_state(conversation),
        "messages": [asdict(m) for m in conversation.messages],
    }
