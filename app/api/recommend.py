import io
import os
import httpx
import traceback
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
    (동일한 content_id를 가진 장소는 중복 없이 유사도가 가장 높은 1개만 반환합니다.)
    """

    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"실패: {str(e)}")

    # 2. 임베딩 추출
    embedding = extract_embedding(image)

    # 3. pgvector 유사도 검색 및 content_id 중복 제거
    try:
        conn = get_db()
        cur  = conn.cursor()

        vec_str = "[" + ",".join(map(str, embedding.tolist())) + "]"

        # [🔥 핵심 수정 포인트] 
        # DISTINCT ON (m.content_id)를 사용하여 중복을 제거합니다.
        # 유사도가 높은 순서대로 정렬(ORDER BY)하여 가장 닮은 스냅샷 딱 하나만 생존시킵니다.
        cur.execute(
            """
            SELECT sub.id, sub.image_id, sub.place_name, sub.region, sub.season, 
                   sub.time, sub.weather, sub.scene, sub.primary_mood, sub.secondary_mood, 
                   sub.caption, sub.content_id, sub.map_lat, sub.map_lng, sub.similarity
            FROM (
                SELECT DISTINCT ON (m.content_id)
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
                    m.map_lat,
                    m.map_lng,
                    1 - (e.embedding <=> %s::vector) AS similarity
                FROM image_embeddings e
                JOIN image_metadata m ON e.id = m.vector_index
                WHERE m.content_id IS NOT NULL
                ORDER BY m.content_id, (e.embedding <=> %s::vector) ASC
            ) sub
            ORDER BY sub.similarity DESC
            LIMIT %s
            """,
            (vec_str, vec_str, top_k),
        )

        rows = cur.fetchall()
        cur.close()
        conn.close()

    except Exception as ex:
        traceback.print_exc()
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
            "map_lat":        row[12],
            "map_lng":        row[13],
            "similarity":     round(float(row[14]) * 100, 1),
        })

    # TourAPI 연동 및 이중 안전막 구성
    async with httpx.AsyncClient() as client:
        for item in results:
            content_id = item.get("content_id")
            if not content_id:
                continue
            try:
                # detail/search 에서 사용했던 필수 파라미터(&firstImageYN=Y&overviewYN=Y&addrinfoYN=Y) 적용
                url = "https://apis.data.go.kr/B551011/KorService2/detailCommon2"
                params = {
                    "serviceKey": TOUR_API_KEY, # 디코딩된 키인지 인코딩된 키인지 꼭 확인하세요! 보통 디코딩 키가 httpx에서 잘 먹힙니다.
                    "contentId": content_id,
                    "MobileOS": "ETC",
                    "MobileApp": "5MinRec",
                    "_type": "json",
                }

                res = await client.get(url, params=params, timeout=5.0)
                                
                if res.status_code == 200:
                    data = res.json()
                    body_data = data.get("response", {}).get("body", {})
                    items_wrapper = body_data.get("items")
                    
                    # 공공 API 특유의 items 데이터가 문자열("")로 터지는 문제 예방 처리 추가
                    if items_wrapper and isinstance(items_wrapper, dict) and "item" in items_wrapper:
                        tour_item_list = items_wrapper["item"]
                        if isinstance(tour_item_list, list) and len(tour_item_list) > 0:
                            tour_item = tour_item_list[0]
                            item["firstimage"] = tour_item.get("firstimage") or tour_item.get("firstimage2") or None
                            item["overview"]   = tour_item.get("overview") or None
                            item['addr1']      = tour_item.get("addr1") or None
                            continue
                
                # 통신 규격이 깨졌거나 파일이 부재할 시 초기화 보장
                item["firstimage"] = None
                item["overview"]   = None
            
            except Exception as e:
                print(f"공공API 오류 ({content_id}): {e}")
                item["firstimage"] = None
                item["overview"]   = None

    return {"results": results}