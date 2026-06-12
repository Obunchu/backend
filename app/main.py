import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models.inference import load_models
from app.api.recommend import router as recommend_router
from app.api.signup import router as signup_router
from app.api.login import router as login_router
from app.api.places import router as places_router
from app.api.bookmarks import router as bookmarks_router
from app.api.views import router as views_router
from app.api.detail import router as detail_router
from app.api.users import router as user_router

from contextlib import asynccontextmanager

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_models()  # 시작 시
    yield

app = FastAPI(title="5MinRec API", lifespan=lifespan)
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recommend_router)
app.include_router(signup_router)
app.include_router(login_router)
app.include_router(places_router)
app.include_router(bookmarks_router)
app.include_router(views_router)
app.include_router(detail_router)
app.include_router(user_router)

@app.get("/")
def root():
    return {"message": "5MinRec API is running!"}