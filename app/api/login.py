
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel
from app.db.database import get_db

router = APIRouter()

class LoginRequest(BaseModel):
    user_id: str
    password: str

@router.post("/login")
def login(data: LoginRequest):
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT * FROM users
            WHERE user_id = %s AND password = %s
            """,
            (data.user_id, data.password)
        )

        user = cur.fetchone()

        cur.close()
        conn.close()

        if not user:
            raise HTTPException(
                detail="아이디 또는 비밀번호가 올바르지 않습니다."
            )

        return {
            "message": "로그인 성공",
            "user_id": user[0],
            "nickname": user[2]
        }

    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))