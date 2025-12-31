from fastapi import APIRouter, Request, Depends
from app.core.auth import get_current_user 

router = APIRouter()

@router.get("/api/book/{chat_id}")
async def book_api(
    chat_id: str,
    request: Request,
    user_uuid: str = Depends(get_current_user) 
):
    book_data = request.app.state.book_service.get_current_book(
        user_uuid=user_uuid,
        chat_id=chat_id,
    )

    return book_data

@router.get("/api/list/curriculum")
async def get_all_curriculum_api(request: Request):

    curriculums = request.app.state.book_service.load_all_curriculums()

    return {"curriculums": curriculums}