import os
import httpx
import asyncio
from fastapi import APIRouter, HTTPException, Query
from app.db.database import get_db
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

TOUR_API_KEY = os.getenv("TOUR_API_KEY")
router = APIRouter()

async def fetch_tour_extra_info(client: httpx.AsyncClient, item: dict):
    content_id = item.get("content_id")
    if not content_id:
        item["firstimage"] = None
        item["overview"] = None
        item["addr1"] = None
        return item

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
                
        if res.status_code == 200:
            data = res.json()
            
            response_obj = data.get("response", {})
            header = response_obj.get("header", {})

            body = response_obj.get("body", {})
            items_wrapper = body.get("items", {})
            
            if items_wrapper and "item" in items_wrapper:
                tour_item = items_wrapper["item"][0]
                item["firstimage"] = tour_item.get("firstimage") or tour_item.get("firstimage2") or None
                item["overview"] = tour_item.get("overview") or None
                item["addr1"] = tour_item.get("addr1") or None
                return item
                
    except Exception as e:
        print(f"공공API 오류 (content_id: {content_id}): {e}")
    
    item["firstimage"] = None
    item["overview"] = None
    item["addr1"] = None
    return item

@router.get("/detail/get")
async def get_tour_detail(content_id: int):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT *
        FROM image_metadata
        WHERE content_id = %s
        """,
        (content_id,)
    )
    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="관광지를 찾을 수 없습니다."
        )
    
    async with httpx.AsyncClient() as client:
        result = await fetch_tour_extra_info(client, result)

    return {"result": result}

@router.get("/detail/search")
async def search_tour_places(
    mood: str = Query(None, description="쉼표로 구분된 무드 키워드"),
    region: str = Query(None, description="쉼표로 구분된 지역 키워드")
):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    base_query = """
        SELECT DISTINCT ON (content_id) 
            id, image_id, place_name, region, season, time, weather, 
            scene, primary_mood, secondary_mood, caption, content_id, 
            map_lat, map_lng, views
        FROM image_metadata
        WHERE 1=1
    """
    
    where_clauses = []
    query_params = []

    if mood:
        mood_list = [m.strip() for m in mood.split(",") if m.strip()]
        if mood_list:
            mood_conditions = []
            for m in mood_list:
                mood_conditions.append("(primary_mood = %s OR secondary_mood = %s)")
                query_params.extend([m, m])
            where_clauses.append(f"({ ' OR '.join(mood_conditions) })")

    if region:
        region_list = [r.strip() for r in region.split(",") if r.strip()]
        if region_list:
            region_conditions = []
            for r in region_list:
                search_reg = r[:2]
                if "경남" in r: search_reg = "경남"
                elif "경북" in r: search_reg = "경북"
                elif "전남" in r: search_reg = "전남"
                elif "전북" in r: search_reg = "전북"
                elif "충남" in r: search_reg = "충남"
                elif "충북" in r: search_reg = "충북"
                
                region_conditions.append("region LIKE %s")
                query_params.append(f"%{search_reg}%")
            where_clauses.append(f"({ ' OR '.join(region_conditions) })")

    if where_clauses:
        full_query = f"{base_query} AND { ' AND '.join(where_clauses) } ORDER BY content_id, id DESC LIMIT 30"
    else:
        full_query = f"{base_query} ORDER BY content_id, id DESC LIMIT 30"

    try:
        cursor.execute(full_query, tuple(query_params))
        db_results = cursor.fetchall()
    except Exception as e:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=500, detail=f"데이터베이스 조회 오류: {str(e)}")
    
    cursor.close()
    conn.close()

    if db_results:
        async with httpx.AsyncClient() as client:
            tasks = [fetch_tour_extra_info(client, item) for item in db_results]
            enriched_results = await asyncio.gather(*tasks)
            return enriched_results

    return []