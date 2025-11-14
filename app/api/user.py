from fastapi import APIRouter, HTTPException, Depends, Query
from app.core import auth
from app.services import user_service
from app.schemas.user import User

router = APIRouter()

# 사용자 정보 조회
@router.get("/api/users/{id}", response_model=User)
def get_user_profile(id: str, _: str = Depends(auth.get_current_user)):
    user_data = user_service.get_user(id)
    if not user_data:
        raise HTTPException(status_code=400, detail="존재하지 않는 사용자입니다.")
    return {
        "id": id,
        "name": user_data["name"],
    }

# 아이디 중복 확인
@router.get("/api/users/{id}/exists")
def check_id(id: str):
    if user_service.get_user(id):
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")
    return {"message": "사용 가능한 아이디입니다."}


# ------------------ ME -------------------

# 내 정보 조회
@router.get("/api/me", response_model=User)
def get_my_profile(uuid: str = Depends(auth.get_current_user)):
    user_data = user_service.get_user_by_access_token(uuid)
    return {
        "id": user_data["id"],
        "name": user_data["name"] if user_data["name"] else "",
    }

# # 회원 탈퇴
# @router.delete("/api/me")
# def quit(req: QuitRequest, user_id: str = Depends(auth.get_current_user)):
#     user_data = user_service.get_user(user_id)
#     if not user_data:
#         raise HTTPException(status_code=400, detail="사용자를 찾을 수 없습니다.")
#     if not user_service.verify_password(req.password, user_data["password"]):
#         raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")
#     if not user_service.delete_user(user_id):
#         raise HTTPException(status_code=400, detail="회원 탈퇴에 실패했습니다.")
#     return {"message": "회원 탈퇴가 완료되었습니다."}