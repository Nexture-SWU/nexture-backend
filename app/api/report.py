from fastapi import APIRouter, Request, Depends
from app.core.auth import get_current_user 

router = APIRouter()

# =================================================
# get
# =================================================

@router.get("/api/report/book/{chat_id}")
async def get_book_report_api(
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


@router.get("/api/report/final/{chat_id}")
async def get_final_report_api(
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

@router.get("/api/list/report/final")
async def get_final_reports_api(
    request: Request,
    user_uuid: str = Depends(get_current_user)
):
    print("user_uuid", user_uuid)
    final_reports = request.app.state.report_service.list_all_final_reports(
        user_uuid=user_uuid,
    )
    
    chat_id, book_data = request.app.state.chat_service.create_chat(user_uuid)

    return {
        "final_reports": final_reports, 
        "chat_id": chat_id,
        "message": "채팅방이 생성되었습니다."}

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

@router.get("/api/list/curriculum")
async def get_all_curriculum_api(request: Request):

    curriculums = request.app.state.report_service.load_all_curriculums()

    return {"curriculums": curriculums}