import os
import httpx
from fastapi import APIRouter
from app.db.database import get_db
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

TOUR_API_KEY = os.getenv("TOUR_API_KEY")
router = APIRouter()

class BookmarkRequest(BaseModel):
    user_id: str
    content_id: int
    place_name: str

class ViewRequest(BaseModel):
    content_id: int

class bookmarkStatusRequest(BaseModel):
    user_id: str
    content_id: int

@router.get("/bookmarks/find")
async def get_bookmarks(user_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT place_name, content_id, created_at 
        FROM bookmarks
        WHERE user_id = %s
        ORDER BY created_at DESC
        """, (user_id, )
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "place_name": row[0],
            "content_id": row[1],
            "created_at": str(row[2]),
            "firstimage": None, 
            "addr1": None      
        })

    async with httpx.AsyncClient() as client:
        for item in results:
            content_id = item.get("content_id")
            if not content_id:
                continue
            try:
                url = "https://apis.data.go.kr/B551011/KorService2/detailCommon2"
                params = {
                    "serviceKey": TOUR_API_KEY, 
                    "contentId": content_id,
                    "MobileOS": "ETC",
                    "MobileApp": "5MinRec",
                    "_type": "json",
                }

                res = await client.get(url, params=params, timeout=5.0)
                data = res.json()

                items_container = data.get("response", {}).get("body", {}).get("items", {})
                if items_container and "item" in items_container:
                    tour_item = items_container["item"][0]
                    item["firstimage"] = tour_item.get("firstimage", None)
                    item["addr1"] = tour_item.get("addr1", None) 
            
            except Exception as e:
                print(f"공공API 오류 ({content_id}): {e}")
                item["firstimage"] = None
                item["addr1"] = None

    return {"results": results}


@router.post("/bookmarks/add")
async def add_bookmark(req: BookmarkRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO bookmarks (user_id, content_id, place_name)
            VALUES (%s, %s, %s)
            """,
            (req.user_id, req.content_id, req.place_name)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return {"ok": True}

@router.post("/bookmarks/remove")
async def check_bookmark(req: bookmarkStatusRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM bookmarks
        WHERE user_id = %s
        AND content_id = %s
    """, (req.user_id, req.content_id))

    conn.commit()

    cursor.close()
    conn.close()

    return {"success": True}


@router.post("/bookmarks/count")
async def add_views(req: ViewRequest):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM bookmarks
        WHERE content_id = %s
    """, (req.content_id,))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    return {"count": row[0]}

@router.post("/bookmarks/check")
async def check_bookmark(req: bookmarkStatusRequest):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM bookmarks
        WHERE user_id = %s
        AND content_id = %s
    """, (req.user_id, req.content_id))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    return {
        "is_bookmarked": row[0] > 0
    }