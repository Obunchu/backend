# backend/api/places.py
import os
import json
import httpx
from fastapi import APIRouter
from dotenv import load_dotenv
from app.db.database import get_db
from math import radians, cos, sin, asin, sqrt

load_dotenv()

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # 지구 반지름 km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return R * 2 * asin(sqrt(a))

router = APIRouter()
TOUR_API_KEY = os.getenv("TOUR_API_KEY")

@router.get("/places/nearby")
async def get_nearby_places(lat: float, lng: float, radius_km: float = 1.0):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT ON (content_id) place_name, content_id, map_lat, map_lng 
        FROM image_metadata 
        WHERE map_lat IS NOT NULL AND map_lng IS NOT NULL
        ORDER BY content_id
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    results = []
    async with httpx.AsyncClient() as client:
        for place_name, content_id, map_lat, map_lng in rows:
            dist = haversine(lat, lng, map_lat, map_lng)
            if dist <= radius_km:
                try:
                    res = await client.get(
                        "https://apis.data.go.kr/B551011/KorService2/detailCommon2",
                        params={
                            "serviceKey": TOUR_API_KEY,
                            "contentId": content_id,
                            "MobileOS": "ETC",
                            "MobileApp": "5MinRec",
                            "_type": "json"
                        }
                    )
                    data = res.json()
                    item = data["response"]["body"]["items"]["item"][0]

                    results.append({
                        "place_name": place_name,
                        "content_id": content_id,
                        "latitude": map_lat,
                        "longitude": map_lng,
                        "distance_km": round(dist, 3),
                        "address": item.get("addr1", ""),
                        "firstimage": item.get("firstimage", ""),
                    })

                except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                    address = ""
                    firstimage = ""

    return results