from fastapi import APIRouter, Request, Depends
from app.schemas.chat import ChatMessageRequest
from app.core.auth import get_current_user 

router = APIRouter()

@router.post("/api/chat/create")
def create_chat(request: Request, user_uuid: str = Depends(get_current_user) ):

    chat_id = request.app.state.chat_service.create_chat(user_uuid)

    return {
        "chat_id": chat_id,
        "message": "채팅방이 생성되었습니다."
    }

@router.post("/api/chat/{chat_id}")
async def chat_api(
    chat_id: str,
    req: ChatMessageRequest,
    request: Request,
    user_uuid: str = Depends(get_current_user) 
):
    llm = request.app.state.llm 

    reply = request.app.state.chat_service.process_chat(
        llm=llm,
        user_uuid=user_uuid,
        chat_id=chat_id,
        user_message=req.message
    )

    return {"reply": reply}