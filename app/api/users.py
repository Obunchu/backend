from fastapi import APIRouter, HTTPException, Query, Depends, status
from app.db.database import get_db
from pydantic import BaseModel, Field
from psycopg2.extensions import connection as Connection

router = APIRouter(prefix="/users", tags=["users"])

class UpdateNicknameRequest(BaseModel):
    nickname: str = Field(..., min_length=1, description="변경할 닉네임")

class UpdatePasswordRequest(BaseModel):
    currentPassword: str = Field(..., description="기존 비밀번호")
    newPassword: str = Field(..., min_length=4, description="새 비밀번호")

class DeleteAccountRequest(BaseModel):
    password: str = Field(..., description="본인 확인용 비밀번호")


@router.patch("/{user_id}/nickname", status_code=status.HTTP_200_OK)
async def update_nickname(user_id: str, data: UpdateNicknameRequest, db: Connection = Depends(get_db)):
    cursor = db.cursor()
    try:
        # 유저 존재 여부 확인 (unique_user_id 제약조건이 있는 user_id 컬럼 기준)
        cursor.execute("SELECT user_id FROM public.users WHERE user_id = %s;", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
        
        # 닉네임 수정 실행
        cursor.execute(
            "UPDATE public.users SET nickname = %s WHERE user_id = %s;",
            (data.nickname, user_id)
        )
        db.commit()
        
        return {"message": "이름 변경이 완료되었습니다.", "nickname": data.nickname}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")
    finally:
        cursor.close()


@router.patch("/{user_id}/password", status_code=status.HTTP_200_OK)
async def update_password(user_id: str, data: UpdatePasswordRequest, db: Connection = Depends(get_db)):
    cursor = db.cursor()
    try:
        # 해당 유저의 비밀번호 가져오기
        cursor.execute("SELECT password FROM public.users WHERE user_id = %s;", (user_id,))
        user_password_row = cursor.fetchone()
        
        if not user_password_row:
            raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
        
        # 기존 비밀번호 일치 여부 확인 (user_password_row[0]은 DB의 password 텍스트)
        if user_password_row[0] != data.currentPassword:
            raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
        
        # 새 비밀번호로 업데이트
        cursor.execute(
            "UPDATE public.users SET password = %s WHERE user_id = %s;",
            (data.newPassword, user_id)
        )
        db.commit()
        
        return {"message": "비밀번호 변경이 완료되었습니다."}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")
    finally:
        cursor.close()


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_account(user_id: str, data: DeleteAccountRequest, db: Connection = Depends(get_db)):
    cursor = db.cursor()
    try:
        # 유저 및 비밀번호 조회
        cursor.execute("SELECT password FROM public.users WHERE user_id = %s;", (user_id,))
        user_password_row = cursor.fetchone()
        
        if not user_password_row:
            raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
        
        # 탈퇴 확인용 비밀번호 검증
        if user_password_row[0] != data.password:
            raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않아 탈퇴할 수 없습니다.")
        
        # 레코드 삭제 실행
        cursor.execute("DELETE FROM public.users WHERE user_id = %s;", (user_id,))
        db.commit()
        
        return {"message": "회원 탈퇴가 완료되었습니다."}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류: {str(e)}")
    finally:
        cursor.close()