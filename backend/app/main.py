import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes import auth, azure, branding, currency, users, vms, workshops

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    os.makedirs("/var/www/lab-console/data", exist_ok=True)
    os.makedirs("/var/www/lab-console/data/branding", exist_ok=True)
    await init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(branding.router)
app.include_router(users.router)
app.include_router(azure.router)
app.include_router(currency.router)
app.include_router(workshops.router)
app.include_router(vms.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
