import httpx
import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.db.database import get_db

load_dotenv()
TOUR_API_KEY = os.getenv("TOUR_API_KEY")

async def fetch_and_save():
    conn = get_db()
    cursor = conn.cursor()

    # 좌표가 아직 없는 것만 조회
    cursor.execute("""
        SELECT id, content_id FROM image_metadata
        WHERE content_id IS NOT NULL
          AND map_lat IS NULL
    """)
    rows = cursor.fetchall()
    print(f"총 {len(rows)}개 처리 시작")

    async with httpx.AsyncClient() as client:
        for id, content_id in rows:
            try:
                res = await client.get(
                    "https://apis.data.go.kr/B551011/KorService2/detailCommon2",
                    params={
                        "serviceKey": TOUR_API_KEY,
                        "contentId": content_id,
                        "MobileOS": "ETC",
                        "MobileApp": "Obunchu",
                        "_type": "json",
                    }
                )
                
                item = res.json()["response"]["body"]["items"]["item"][0]
                map_lat = float(item["mapy"])
                map_lng = float(item["mapx"])

                cursor.execute("""
                    UPDATE image_metadata
                    SET map_lat = %s, map_lng = %s
                    WHERE id = %s
                """, (map_lat, map_lng, id))
                conn.commit()
                print(f"✅ content_id {content_id} 저장 완료")

                await asyncio.sleep(0.2)  # API 블락 방지용 딜레이

            except Exception as e:
                print(f"❌ content_id {content_id} 실패: {e}")
                continue

    cursor.close()
    conn.close()

asyncio.run(fetch_and_save())