from fastapi import APIRouter, Request, Depends
from app.schemas.chat import ChatMessageRequest, BookReportRequest
from app.core.auth import get_current_user 

router = APIRouter()

# =================================================
# post
# =================================================

@router.post("/api/chat/create")
def create_chat_id(request: Request, user_uuid: str = Depends(get_current_user) ):
    chat_id, book_data = request.app.state.chat_service.create_chat(user_uuid)

    return {
        "chat_id": chat_id,
        "book_data": book_data,
        "message": "채팅방이 생성되었습니다."
    }

@router.post("/api/chat/{chat_id}/message")
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
    request.app.state.chat_service.create_book_report(
        user_uuid=user_uuid,
        chat_id=chat_id,
        subject=req.subject,
        summary=req.summary,
        book_review=req.book_review,
        debate_review=req.debate_review
    )

    return {"message": "감상문이 성공적으로 저장되었습니다."}


@router.post("/api/chat/{chat_id}/final-report")
async def report_api(
    chat_id: str,
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    llm = request.app.state.llm

    final_report = request.app.state.chat_service.create_final_report(
        llm=llm,
        user_uuid=user_uuid,
        chat_id=chat_id
    )

    return {"final_report": final_report}

# =================================================
# get
# =================================================

@router.get("/api/chat/list")
def list_chats(request: Request, user_uuid: str = Depends(get_current_user) ):
    chats = request.app.state.chat_service.list_chats(user_uuid)

    return {"chats": chats}

@router.get("/api/chat/{chat_id}/message")
async def book_report_api(
    chat_id: str,
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    chat = request.app.state.chat_service.get_chat_detail(
        user_uuid=user_uuid,
        chat_id=chat_id,
        mode="chat_messages"
    )

    return {"chat": chat}

@router.get("/api/chat/{chat_id}/book-report")
async def book_report_api(
    chat_id: str,
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    book_report = request.app.state.chat_service.get_chat_detail(
        user_uuid=user_uuid,
        chat_id=chat_id,
        mode="book_report"
    )

    return {"book_report": book_report}


@router.get("/api/chat/{chat_id}/final-report")
async def report_api(
    chat_id: str,
    request: Request,
    user_uuid: str = Depends(get_current_user)
):

    final_report = request.app.state.chat_service.get_chat_detail(
        user_uuid=user_uuid,
        chat_id=chat_id,
        mode="final_report"
    )

    return {"final_report": final_report}
