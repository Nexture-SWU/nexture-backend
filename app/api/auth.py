from fastapi import APIRouter, HTTPException
from app.schemas.user import RequestUserCreate, RequestUserLogin, ResponseUserLogin
from app.services import user_service

router = APIRouter()

# 회원가입
@router.post("/api/auth/join")
def join(user: RequestUserCreate):
    try:
        user_service.create_user(user)
        return {"message": "회원가입 성공"}
    except Exception:
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")

# 로그인
@router.post("/api/auth/login", response_model=ResponseUserLogin)
def login(data: RequestUserLogin):
    user_data, access_token = user_service.get_user(data.id, True)

    if not user_data:
        raise HTTPException(status_code=400, detail="사용자가 존재하지 않습니다.")

    if not user_service.verify_password(data.password, user_data["password"]):
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    return {
        "id": user_data["id"],
        "name": user_data["name"],
        "access_token": access_token,
    }