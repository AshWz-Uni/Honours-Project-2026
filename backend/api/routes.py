from fastapi import APIRouter
from backend.api.models import ChatRequest, ChatResponse
from backend.agent.tutor_agent import generate_tutor_response

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):

    response = generate_tutor_response(
        code=request.code,
        question=request.question
    )

    return ChatResponse(response=response)
