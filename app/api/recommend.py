import io
from fastapi import APIRouter, File, UploadFile, HTTPException
from PIL import Image
from pillow_heif import register_heif_opener
from app.models.inference import extract_embedding
from app.db.database import get_db

register_heif_opener()

router = APIRouter()

@router.post("/recommend")
async def recommend(file: UploadFile = File(...), top_k: int = 5):
    """
    이미지를 받아 유사한 한국 관광지 top_k개를 반환합니다.
    """

    print(f"받은 파일: {file.filename}, 타입: {file.content_type}")
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
    
    # 4. 결과 직렬화
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
            "content_id":     int(row[11]) if row[11] is not None else None,  # ← 수정
            "similarity":     round(float(row[12]) * 100, 1),  # % 로 변환
        })

    return {"results": results}
