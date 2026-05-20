"""API für AI Ticket System; optionale Anbindung an Zammad (REST)."""
import os

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="AI Ticket API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ZAMMAD_BASE = os.getenv("ZAMMAD_INTERNAL_URL", "").rstrip("/")
ZAMMAD_TOKEN = os.getenv("ZAMMAD_API_TOKEN", "").strip()
ZAMMAD_GROUP_ID = int(os.getenv("ZAMMAD_DEFAULT_GROUP_ID", "1"))



def _zammad_headers() -> dict[str, str]:
    if not ZAMMAD_TOKEN:
        return {}
    return {"Authorization": f"Token token={ZAMMAD_TOKEN}"}


@app.get("/")
def root():
    return {
        "message": "AI Ticket Management Backend läuft"
    }


@app.get("/status")
def status():
    return {
        "status": "online"
    }


@app.get("/health")
def health():
    return {
        "healthy": True
    }