from datetime import timedelta
from app.core.database import db
from app.core import auth
from passlib.context import CryptContext
from app.schemas.user import RequestUserCreate
from google.cloud.firestore_v1.field_path import FieldPath  
from app.utils.common import generate_uuid_with_timestamp

# 비밀번호 해싱 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 사용자 존재 확인
def is_user(user_id: str):
    existing = db.collection("users").where("id", "==", user_id).get()
    if existing:
        return existing[0]
    else:
        return False

def get_user_by_access_token(uuid: str):
    """
    uuid를 기반으로 사용자 정보를 조회합니다.
    """
    user_doc = db.collection("users").document(uuid).get()
    if user_doc:
        user_data = user_doc.to_dict()
        
        return user_data
    return None


def get_user(user_id: str, for_login: bool = False):
    """
    user_id를 기반으로 사용자 정보를 조회합니다.
    """
    user_doc = is_user(user_id)

    if user_doc:
        user_data = user_doc.to_dict()
        user_uuid = user_doc.id
        if for_login:
            access_token = auth.create_access_token(
                                data={"sub": user_uuid},
                                expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
                            )

            return user_data, access_token
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
    })

# 비밀번호 검증
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    사용자가 입력한 비밀번호와 DB에 저장된 해시값을 비교합니다.
    """
    return pwd_context.verify(plain_password, hashed_password)

# 사용자 및 관련 데이터 삭제
def delete_user(user_id: str)->bool:
    """
    회원 탈퇴 처리. 사용자 계정, 팔로우 관계 등을 모두 삭제합니다.
    """
    try:
        db.collection("users").document(user_id).delete()
        follows = db.collection("follow").where("follower_id", "==", user_id).stream()
        for doc in follows:
            doc.reference.delete()

        follows = db.collection("follow").where("followee_id", "==", user_id).stream()
        for doc in follows:
            doc.reference.delete()        

        return True
    except Exception as e:
        print(f"[ERROR] 유저 삭제 실패: {e}")
        return False

    """
    주어진 접두사(prefix)를 기반으로 사용자 ID를 검색합니다.
    - 사용자 문서 ID 기준으로 검색합니다 (document_id 사용).
    - 최대 5명의 사용자만 검색됩니다.
    - 각 사용자에 대해 기본 정보(id, uid, profileImage, userName)를 포함합니다.
    - 각 사용자에 대해 followers(자신을 팔로우하는 사람들) 및 following(자신이 팔로우하는 사람들) 목록도 함께 반환합니다.
    """
    try:
        start = prefix
        end = prefix + "\uf8ff"

        # 먼저 유저 검색
        user_query = (
            db.collection("users")
            .order_by(FieldPath.document_id())
            .start_at([start])
            .end_at([end])
            .limit(5)
            .stream()
        )

        # 검색된 유저 ID들 수집
        users = []
        user_ids = []
        for doc in user_query:
            data = doc.to_dict()
            target_user_id = doc.id

            users.append({
                "id": target_user_id,
                "uid": data.get("uid"),
                "profileImage": data.get("profileImage"),
                "userName": data.get("userName"),
            })
            user_ids.append(target_user_id)

        # isFollowing 추가
        for user in users:
            target_id = user["id"]

            # followers: 그 사용자를 팔로우하는 사람들
            follower_docs = db.collection("follow").where("followee_id", "==", target_id).stream()
            followers = [doc.to_dict().get("follower_id") for doc in follower_docs]

            # following: 그 사용자가 팔로우하는 사람들
            following_docs = db.collection("follow").where("follower_id", "==", target_id).stream()
            following = [doc.to_dict().get("followee_id") for doc in following_docs]

            user["followers"] = followers
            user["following"] = following
        return users

    except Exception as e:
        print("Error:", e)
        return []