import os
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from PIL import Image
from transformers import CLIPVisionModelWithProjection, CLIPProcessor
from peft import PeftModel

# ──────────────────────────────────────────
# 경로 설정
# ──────────────────────────────────────────
BASE_DIR          = os.path.dirname(__file__)
VISION_LORA_PATH  = os.path.join(BASE_DIR, "vision_lora")   # LoRA 가중치 폴더
HEADS_PT_PATH     = os.path.join(BASE_DIR, "custom_heads.pt")
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
# 전역 모델 변수
# ──────────────────────────────────────────
device         = torch.device("cuda" if torch.cuda.is_available() else "cpu")
vision_encoder = None
processor      = None
proj_head      = None

def load_models():
    global vision_encoder, processor, proj_head
 
    print("⏳ Vision Encoder 로드 중...")
    base_vision    = CLIPVisionModelWithProjection.from_pretrained(VISION_BASE_MODEL)
    vision_encoder = PeftModel.from_pretrained(base_vision, VISION_LORA_PATH).to(device)
    vision_encoder.eval()
 
    processor = CLIPProcessor.from_pretrained(VISION_BASE_MODEL)
 
    print("⏳ Custom Heads 로드 중...")
    _proj_head  = ProjectionHead().to(device)
    _scene_head = SceneHead().to(device)
    _txt_proj   = nn.Linear(768, 512).to(device)
 
    heads_state = torch.load(HEADS_PT_PATH, map_location=device)
    _proj_head.load_state_dict(heads_state["proj_head"])
    _scene_head.load_state_dict(heads_state["scene_head"])
    _txt_proj.load_state_dict(heads_state["txt_proj_layer"])
 
    _proj_head.eval()
    proj_head = _proj_head
 
    print("✅ 모든 모델 로드 완료!")
 

def extract_embedding(image: Image.Image) -> np.ndarray:
    if vision_encoder is None or processor is None or proj_head is None:
        raise RuntimeError("모델이 로드되지 않았습니다. load_models()를 먼저 호출하세요.")
 
    inputs       = processor(images=image, return_tensors="pt")
    pixel_values = inputs["pixel_values"].to(device)
 
    with torch.no_grad():
        img_feat  = vision_encoder(pixel_values=pixel_values).image_embeds  # (1, 512)
        embedding = proj_head(img_feat)                                       # (1, 256)
 
    return embedding.cpu().numpy()[0]  # (256,)
 