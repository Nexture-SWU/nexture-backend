from fastapi import APIRouter, Request, Depends
from app.schemas.chat import BookReportRequest
from app.core.auth import get_current_user 

router = APIRouter()

# =================================================
# post
# =================================================
@router.post("/api/report/book/{chat_id}")
async def create_book_report_api(
    chat_id: str,
    req: BookReportRequest,
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    request.app.state.report_service.create_book_report(
        user_uuid=user_uuid,
        chat_id=chat_id,
        subject=req.subject,
        summary=req.summary,
        book_review=req.book_review,
        debate_review=req.debate_review
    )

    return {"message": "감상문이 성공적으로 저장되었습니다."}


@router.post("/api/report/final/{chat_id}")
async def create_final_report_api(
    chat_id: str,
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    llm = request.app.state.llm

    final_report = request.app.state.report_service.create_final_report(
        llm=llm,
        user_uuid=user_uuid,
        chat_id=chat_id
    )
    chat_id, book_data = request.app.state.chat_service.create_chat(user_uuid)

    return {"final_report": final_report,         
            "chat_id": chat_id,
            "message": "채팅방이 생성되었습니다."}

@router.post("/api/report/total")
async def create_total_report_api(
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    llm = request.app.state.llm
    total_report = request.app.state.report_service.create_total_report(llm, user_uuid)

    return {"total_report": total_report}

# =================================================
# get
# =================================================

@router.get("/api/report/book/{chat_id}")
async def get_book_report_api(
    chat_id: str,
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    book_report = request.app.state.report_service.get_report_detail(
        user_uuid=user_uuid,
        chat_id=chat_id,
        mode="book_report"
    )

    return {"book_report": book_report}

@router.get("/api/report/final/{chat_id}")
async def get_final_report_api(
    chat_id: str,
    request: Request,
    user_uuid: str = Depends(get_current_user)
):

    final_report = request.app.state.report_service.get_report_detail(
        user_uuid=user_uuid,
        chat_id=chat_id,
        mode="final_report"
    )

    return {"final_report": final_report}

@router.get("/api/report/total")
async def get_total_report_api(
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    total_report = request.app.state.report_service.get_total_report(user_uuid)
    
    return { "total_report" : total_report}

@router.get("/api/list/report/final")
async def get_final_reports_api(
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    print("user_uuid", user_uuid)
    final_reports = request.app.state.report_service.list_all_final_reports(
        user_uuid=user_uuid,
    )
    
    return {
        "final_reports": final_reports}

@router.get("/api/list/report/book")
async def get_book_reports_api(
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    print("user_uuid", user_uuid)
    book_reports = request.app.state.report_service.list_all_book_reports(
        user_uuid=user_uuid,
    )

    return {"book_reports": book_reports}

