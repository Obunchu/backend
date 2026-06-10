from fastapi import HTTPException, APIRouter
from pydantic import BaseModel
from app.db.database import get_db

router = APIRouter()

class SignupRequest(BaseModel):
    user_id: str
    nickname: str
    password: str

@router.post("/signup")
def signup(data: SignupRequest):
    try:
        conn = get_db()
        cur = conn.cursor()

        # 중복 확인
        cur.execute(
            "SELECT * FROM users WHERE user_id = %s",
            (data.user_id,)
        )

        existing_user = cur.fetchone()

        if existing_user:
            raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")

        # 회원 저장
        cur.execute(
            """
            INSERT INTO users (user_id, password, nickname)
            VALUES (%s, %s, %s)
            """,
            (data.user_id, data.password, data.nickname)
        )

        conn.commit()

        cur.close()
        conn.close()

        return {"message": "회원가입 성공"}

    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))