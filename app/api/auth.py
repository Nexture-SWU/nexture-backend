from fastapi import APIRouter, HTTPException, Request, Depends
from app.schemas.user import RequestUserCreate, RequestUserLogin, ResponseUserLogin, ResponseUserReissue
from app.services import user_service

from app.core import auth

router = APIRouter()

# 회원가입
@router.post("/api/auth/join")
def join(user: RequestUserCreate):
    try:
        user_service.create_user(user)
        return {"message": "회원가입 성공"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"이미 존재하는 아이디입니다.: {str(e)}")

# 로그인
@router.post("/api/auth/login", response_model=ResponseUserLogin)
def login(data: RequestUserLogin):
    user_data, access_token, refresh_token = user_service.get_user_by_id(data.id, for_login=True)

    if not user_data:
        raise HTTPException(status_code=400, detail="사용자가 존재하지 않습니다.")

    if not user_service.verify_password(data.password, user_data["password"]):
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }

@router.post("/api/auth/reissue", response_model=ResponseUserReissue)
def reissue_token(request: Request, user_uuid: str = Depends(auth.get_current_user)):
    auth_header = request.headers.get("authorization")
    refresh_token = auth_header.split(" ")[1]
    access_token, refresh_token = user_service.get_user_by_uuid(user_uuid = user_uuid, for_reissue=True, refresh_token=refresh_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }
