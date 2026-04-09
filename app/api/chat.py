from __future__ import annotations

from fastapi import APIRouter, Depends

from app.chat.service import ChatService, get_chat_service
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return chat_service.answer(request)
