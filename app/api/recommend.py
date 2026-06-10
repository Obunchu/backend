import io
import os
import httpx
from fastapi import APIRouter, File, UploadFile, HTTPException
from PIL import Image
from pillow_heif import register_heif_opener
from app.models.inference import extract_embedding
from app.db.database import get_db
from dotenv import load_dotenv

load_dotenv()
register_heif_opener()

router = APIRouter()

TOUR_API_KEY = os.getenv("TOUR_API_KEY")

@router.post("/recommend")
async def recommend(file: UploadFile = File(...), top_k: int = 5):
    """
    이미지를 받아 유사한 한국 관광지 top_k개를 반환합니다.
    """

    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception as e:
        traceback.print_exc()  # ← 추가
        raise HTTPException(status_code=400, detail=f"실패: {str(e)}")

    # 2. 임베딩 추출
    embedding = extract_embedding(image)

    # 3. pgvector 유사도 검색
    try:
        conn = get_db()
        cur  = conn.cursor()

        vec_str = "[" + ",".join(map(str, embedding.tolist())) + "]"

        cur.execute(
            """
            SELECT
                m.id,
                m.image_id,
                m.place_name,
                m.region,
                m.season,
                m.time,
                m.weather,
                m.scene,
                m.primary_mood,
                m.secondary_mood,
                m.caption,
                m.content_id,
                1 - (e.embedding <=> %s::vector) AS similarity
            FROM image_embeddings e
            JOIN image_metadata m ON e.id = m.vector_index
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (vec_str, vec_str, top_k),
        )

        rows = cur.fetchall()
        cur.close()
        conn.close()

    except Exception as ex:
        import traceback
        traceback.print_exc()  # ← 이 줄 추가
        raise HTTPException(status_code=500, detail=f"DB 오류: {str(ex)}")
    
    results = []
    for row in rows:
        results.append({
            "id":             row[0],
            "image_id":       row[1],
            "place_name":     row[2],
            "region":         row[3],
            "season":         row[4],
            "time":           row[5],
            "weather":        row[6],
            "scene":          row[7],
            "primary_mood":   row[8],
            "secondary_mood": row[9],
            "caption":        row[10],
            "content_id":     int(row[11]) if row[11] is not None else None,
            "similarity":     round(float(row[12]) * 100, 1),
        })


    async with httpx.AsyncClient() as client:
        for item in results:
            content_id = item.get("content_id")
            if not content_id:
                continue
            try:
                url = (
                    f"https://apis.data.go.kr/B551011/KorService2/detailCommon2"
                    f"?serviceKey={TOUR_API_KEY}"
                    f"&contentId={content_id}&MobileOS=ETC&MobileApp=5MinRec&_type=json"
                )
                res = await client.get(url)
                data = res.json()

                tour_item = data["response"]["body"]["items"]["item"][0]
                item["firstimage"] = tour_item.get("firstimage", None)
                item["overview"]   = tour_item.get("overview", None)
            
            except Exception as e:
                print(f"공공API 오류 ({content_id}): {e}")
                item["firstimage"] = None
                item["overview"]   = None

    return {"results": results}