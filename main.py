import os
import io
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import psycopg2
from dotenv import load_dotenv

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from transformers import CLIPVisionModelWithProjection, CLIPProcessor
from peft import PeftModel

# ──────────────────────────────────────────
# 앱 초기화
# ──────────────────────────────────────────
app = FastAPI(title="5MinRec API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────
# 경로 설정
# ──────────────────────────────────────────
BASE_DIR          = os.path.dirname(__file__)
VISION_LORA_PATH  = os.path.join(BASE_DIR, "models", "vision_lora")   # LoRA 가중치 폴더
HEADS_PT_PATH     = os.path.join(BASE_DIR, "models", "custom_heads.pt")
VISION_BASE_MODEL = "openai/clip-vit-base-patch32"

# ──────────────────────────────────────────
# Custom Head 정의 (코랩과 동일하게)
# ──────────────────────────────────────────
class ProjectionHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 256),
        )
    def forward(self, x):
        return F.normalize(self.net(x), dim=-1)

class SceneHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 13),
        )
    def forward(self, x):
        return self.net(x)

# ──────────────────────────────────────────
# 모델 로드 (서버 시작 시 1회)
# ──────────────────────────────────────────
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print("⏳ Vision Encoder 로드 중...")
base_vision = CLIPVisionModelWithProjection.from_pretrained(VISION_BASE_MODEL)
vision_encoder = PeftModel.from_pretrained(base_vision, VISION_LORA_PATH).to(device)
vision_encoder.eval()

processor = CLIPProcessor.from_pretrained(VISION_BASE_MODEL)

print("⏳ Custom Heads 로드 중...")
proj_head  = ProjectionHead().to(device)
scene_head = SceneHead().to(device)
txt_proj_layer = nn.Linear(768, 512).to(device)

heads_state = torch.load(HEADS_PT_PATH, map_location=device)
proj_head.load_state_dict(heads_state["proj_head"])
scene_head.load_state_dict(heads_state["scene_head"])
txt_proj_layer.load_state_dict(heads_state["txt_proj_layer"])

proj_head.eval()
scene_head.eval()
txt_proj_layer.eval()

print("✅ 모든 모델 로드 완료!")

# ──────────────────────────────────────────
# DB 연결
# ──────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

# ──────────────────────────────────────────
# 이미지 → 256차원 임베딩 추출
# ──────────────────────────────────────────
def extract_embedding(image: Image.Image) -> np.ndarray:
    inputs = processor(images=image, return_tensors="pt")
    pixel_values = inputs["pixel_values"].to(device)

    with torch.no_grad():
        img_feat = vision_encoder(pixel_values=pixel_values).image_embeds  # (1, 512)
        embedding = proj_head(img_feat)                                      # (1, 256)

    return embedding.cpu().numpy()[0]  # (256,)

# ──────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "5MinRec API is running!"}


@app.post("/recommend")
async def recommend(file: UploadFile = File(...), top_k: int = 5):
    """
    이미지를 받아 유사한 한국 관광지 top_k개를 반환합니다.
    """
    # 1. 이미지 읽기
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="이미지를 읽을 수 없습니다.")

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
