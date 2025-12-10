from datetime import timedelta
from app.core.database import db
from app.core import auth
from passlib.context import CryptContext
from app.schemas.user import RequestUserCreate
from google.cloud.firestore_v1.field_path import FieldPath  
from app.utils.common import generate_uuid_with_timestamp
from datetime import datetime, timezone

# 비밀번호 해싱 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 사용자 존재 확인
def is_user(user_id: str):
    existing = db.collection("users").where("id", "==", user_id).get()
    if existing:
        return existing[0]
    else:
        return False

def save_refresh_token(user_uuid: str, refresh_token: str):
    db.collection("users").document(user_uuid).update({
        "refresh_token": refresh_token,
        "refresh_token_created": datetime.now(timezone.utc)
    })

def get_user_by_uuid(user_uuid: str, for_reissue: bool=False, refresh_token: str=None):
    """
    uuid를 기반으로 사용자 정보를 조회합니다.
    """
    user_doc = db.collection("users").document(user_uuid).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        if for_reissue:
            stored_refresh = user_data.get("refresh_token")
            if stored_refresh != refresh_token:
                raise user_data(status_code=401, detail="Refresh token이 올바르지 않습니다. 다시 로그인 해주세요.")
            
            new_access_token = auth.create_access_token(data={"sub": user_uuid})

            # refresh token 재발급 여부 (보안정책에 따라 결정)
            new_refresh_token = auth.create_refresh_token({"sub": user_uuid})
            save_refresh_token(user_uuid, new_refresh_token)

            return new_access_token, new_refresh_token
        
        else:
            return user_data
    return None



def get_user_by_id(user_id: str, for_login: bool = False):
    """
    user_id를 기반으로 사용자 정보를 조회합니다.
    """
    user_doc = is_user(user_id)

    if user_doc:
        user_data = user_doc.to_dict()
        user_uuid = user_doc.id
        if for_login:
            access_token = auth.create_access_token(data={"sub": user_uuid})
            refresh_token = auth.create_refresh_token(data={"sub": user_uuid})
            save_refresh_token(user_uuid, refresh_token)
            return user_data, access_token, refresh_token
        else:
            return user_data

    return None
    


# 사용자 생성 (회원가입)
def create_user(user: RequestUserCreate):
    """
    신규 사용자 등록. 아이디 중복 여부를 확인하고,
    비밀번호는 해시 처리되며, 프로필 이미지는 저장됩니다.
    """

    uuid = generate_uuid_with_timestamp()
    user_ref = db.collection("users").document(uuid)

    # 아이디 중복 체크
    if is_user(user.id):
        raise ValueError("이미 존재하는 사용자 ID입니다.")

    hashed_pw = pwd_context.hash(user.password)

    user_ref.set({
        "id": user.id,
        "password": hashed_pw,
        "name": user.name,
        "role": user.role,
        "relation": user.relation,
        "created_at": datetime.now(timezone.utc)
    })

# 비밀번호 검증
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    사용자가 입력한 비밀번호와 DB에 저장된 해시값을 비교합니다.
    """
    return pwd_context.verify(plain_password, hashed_password)

# 사용자 및 관련 데이터 삭제
def delete_user(user_uuid: str)->bool:
    """
    회원 탈퇴 처리. 사용자 계정, 팔로우 관계 등을 모두 삭제합니다.
    """
    try:
        db.collection("users").document(user_uuid).delete()
        return True
    except Exception as e:
        print(f"[ERROR] 유저 삭제 실패: {e}")
        return False

def search_users_by_login_id_prefix(prefix: str, limit: int = 5):
    """
    prefix 기반으로 사용자 아이디를 검색합니다.
    """
    try:
        start = prefix
        end = prefix + "\uf8ff"

        query = (
            db.collection("users")
            .order_by("id")
            .start_at([start])
            .end_at([end])
            .limit(limit)
            .stream()
        )

        users = []
        for doc in query:
            data = doc.to_dict()
            users.append({
                "id": data.get("id"),
                "name": data.get("name"),
                "role": data.get("role"),
            })

        return users

    except Exception as e:
        print("Error:", e)
        return []

def update_user_relation(user_uuid: str, other_user_id: str) -> bool:
    """
    현재 로그인한 user_uuid 유저의 relation 필드에
    other_user_id(로그인 ID)의 유저 문서 UUID를 저장합니다.
    단, 두 유저의 role 이 달라야 합니다.
    """
    try:
        # 1) 현재 로그인한 유저 데이터 조회
        current_user_ref = db.collection("users").document(user_uuid)
        current_user_doc = current_user_ref.get()

        if not current_user_doc.exists:
            print("[ERROR] 현재 로그인한 유저 문서가 존재하지 않음.")
            return False

        current_user = current_user_doc.to_dict()
        current_user_role = current_user.get("role")

        if current_user_role is None:
            print("[ERROR] 현재 유저 role 없음.")
            return False

        # 2) other_user_id 를 가진 대상 유저 조회 (id 필드로 검색)
        docs = db.collection("users").where(filter=FieldPath("id"), op_string="==", value=other_user_id).limit(1).stream()

        target_user_doc = None
        for doc in docs:
            target_user_doc = doc
            break

        if target_user_doc is None:
            print("[INFO] other_user_id 를 가진 유저가 존재하지 않음.")
            return False

        target_user = target_user_doc.to_dict()
        target_user_uuid = target_user_doc.id
        target_user_role = target_user.get("role")

        if target_user_role is None:
            print("[ERROR] 대상 유저 role 없음.")
            return False

        # 3) role 비교 (달라야 함)
        if current_user_role == target_user_role:
            print("[INFO] 두 유저의 역할(role)이 같아서 relation 불가.")
            return False

        # 4) relation 업데이트
        current_user_ref.update({
            "relation": target_user_uuid
        })

        print(f"[INFO] relation 업데이트 성공: {user_uuid} → {target_user_uuid}")
        return True

    except Exception as e:
        print("[ERROR] 유저 relation 업데이트 실패:", e)
        return False