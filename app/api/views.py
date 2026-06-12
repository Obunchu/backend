import os
import httpx
from fastapi import APIRouter
from app.db.database import get_db
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

TOUR_API_KEY = os.getenv("TOUR_API_KEY")
router = APIRouter()

class ViewRequest(BaseModel):
    content_id: int

@router.post("/views/add")
async def add_views(req: ViewRequest):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE image_metadata
        SET views = views + 1
        WHERE content_id = %s
    """, (req.content_id,))

    conn.commit()

    cursor.execute("""
        SELECT views
        FROM image_metadata
        WHERE content_id = %s
    """, (req.content_id,))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    return {"views": row[0]}