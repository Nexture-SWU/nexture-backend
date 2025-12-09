from fastapi import APIRouter, HTTPException, Depends, Query
from app.core import auth
from app.services import user_service
from app.schemas.user import User

router = APIRouter()

# 사용자 검색
@router.get("/api/users/search")
def search_user_ids(prefix: str = Query(..., description="검색할 아이디 prefix"),
                    limit: int = Query(5, description="검색 결과 제한 수")):

    users = user_service.search_users_by_login_id_prefix(prefix, limit)
    
    return {
        "prefix": prefix,
        "count": len(users),
        "results": users
    }

# 사용자 정보 조회
@router.get("/api/users/{id}", response_model=User)
def get_user_profile(id: str, _: str = Depends(auth.get_current_user)):
    user_data = user_service.get_user(id)
    if not user_data:
        raise HTTPException(status_code=400, detail="존재하지 않는 사용자입니다.")
    return {
        "id": id,
        "name": user_data["name"],
        "role": user_data["role"],
    }

# 아이디 중복 확인
@router.get("/api/users/{id}/exists")
def get_check_id(id: str):
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
        "role": user_data["role"],
    }