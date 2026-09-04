from fastapi import APIRouter, HTTPException

from backend.agent.conversation import get_conversation
from backend.agent.tutor_agent import STAGES, generate_tutor_response
from backend.api.models import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        response, conversation_id = generate_tutor_response(
            code=request.code,
            question=request.question,
            conversation_id=request.conversation_id,
            language=request.language,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Tutor model error: {exc}") from exc

    conversation = get_conversation(conversation_id)
    stage = None
    if conversation is not None:
        stage = STAGES[min(conversation.stage, len(STAGES) - 1)]

    return ChatResponse(
        response=response,
        conversation_id=conversation_id,
        stage=stage,
    )


@router.delete("/chat/{conversation_id}")
def clear_chat(conversation_id: str):
    from backend.agent.conversation import clear_conversation

    if not clear_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"message": "Conversation cleared"}
