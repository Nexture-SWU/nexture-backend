from fastapi import APIRouter, HTTPException, Request, Depends
from app.schemas.chat import ChatMessageRequest, BookReportRequest
from app.core.auth import get_current_user 

router = APIRouter()

@router.post("/api/chat/list")
def list_chats(request: Request, user_uuid: str = Depends(get_current_user) ):
    chats = request.app.state.chat_service.list_chats(user_uuid)

    return {"chats": chats}

@router.post("/api/chat/create")
def create_chat(request: Request, user_uuid: str = Depends(get_current_user) ):

    chat_id, book_data = request.app.state.chat_service.create_chat(user_uuid)

    return {
        "chat_id": chat_id,
        "book_data": book_data,
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


@router.post("/api/chat/{chat_id}/book-report")
async def book_report_api(
    chat_id: str,
    req: BookReportRequest,
    request: Request,
    user_uuid: str = Depends(get_current_user) 
):

    message = request.app.state.chat_service.process_book_report(
        user_uuid=user_uuid,
        chat_id=chat_id,
        subject=req.subject,
        summary=req.summary,
        book_review=req.book_review,
        debate_review=req.debate_review
    )

    if message:
        message = "감상문이 성공적으로 저장되었습니다."
        return {"message": message}
    else:
        HTTPException(status_code=500, detail="감상문 저장에 실패했습니다.")