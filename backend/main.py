"""API für AI Ticket System; optionale Anbindung an Zammad (REST)."""
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

app = FastAPI(title="AI Ticket API")

# Erlaubt Frontend-Zugriffe (z. B. Streamlit oder React) auf die API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Liest die interne Zammad-URL aus den Docker-/Systemvariablen
ZAMMAD_BASE = (os.getenv("ZAMMAD_INTERNAL_URL", "http://localhost:8080")
               .rstrip("/"))
# Liest das persönliche API-Token für die Zammad-Authentifizierung
ZAMMAD_TOKEN = os.getenv("ZAMMAD_API_TOKEN", "").strip()


class TicketCreate(BaseModel):
    title: str
    description: str
    customer: str


# Zammad API Authentication via HTTP Token
#https://docs.zammad.org/en/latest/api/intro.html#authentication
def _zammad_headers() -> dict[str, str]:
    if not ZAMMAD_TOKEN:
        return {}
    return {"Authorization": f"Token token={ZAMMAD_TOKEN}"}


# Einfacher Health-Check für Docker, Monitoring oder Tests
@app.get("/health")
def health():
    return {"status": "ok"}


# Basis-Endpunkt der API
@app.get("/")
def root():
    return {"message": "AI Ticket Backend"}


# Endpoint zum Prüfen der Zammad-Verbindung und API-Erreichbarkeit
#https://docs.zammad.org/en/latest/api/intro.html#endpoints-and-example-data
@app.get("/integrations/zammad/status")
def zammad_status() -> dict[str, Any]:
    """Prüft die Erreichbarkeit von Zammad und validiert optional das API-Token."""
    out: dict[str, Any] = {
        "base_url_configured": bool(ZAMMAD_BASE),
        "base_url": ZAMMAD_BASE,
        "token_configured": bool(ZAMMAD_TOKEN),
        "reachable": False,
        "api_ok": False,
        "detail": None,
    }
    try:
        with httpx.Client(timeout=8.0) as client:
            ping = client.get(f"{ZAMMAD_BASE}/", follow_redirects=True)
            out["reachable"] = ping.status_code < 500
            if not ZAMMAD_TOKEN:
                out["detail"] = "Setze ZAMMAD_API_TOKEN (Persönliches Zugangs-Token in Zammad) für API-Zugriff."
                return out
            me = client.get(f"{ZAMMAD_BASE}/api/v1/users/me", headers=_zammad_headers())
            out["api_ok"] = me.status_code == 200
            if me.status_code == 200:
                data = me.json()
                out["user"] = {"id": data.get("id"), "login": data.get("login")}
            elif me.status_code == 401:
                out["detail"] = "Zammad antwortet, aber Token abgelehnt (401)."
            else:
                out["detail"] = f"users/me HTTP {me.status_code}"
    except httpx.RequestError as e:
        out["detail"] = str(e)
    return out

# Tickets über die Zammad REST API abrufen
# https://docs.zammad.org/en/latest/api/ticket/index.html
@app.get("/integrations/zammad/tickets")
def zammad_tickets(limit: int = 10) -> list[dict[str, Any]]:
    """Listet Tickets über die Zammad-API (benötigt ZAMMAD_API_TOKEN)."""
    if not ZAMMAD_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ZAMMAD_API_TOKEN ist nicht gesetzt.",
        )
    limit = max(1, min(limit, 100))     # Begrenzung des Limits zum Schutz vor zu großen API-Anfragen
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{ZAMMAD_BASE}/api/v1/tickets",
                headers=_zammad_headers(),
                params={"per_page": limit, "page": 1},  # Lädt die erste Seite der Tickets mit begrenzter Anzahl
            )
            if r.status_code == 401:
                raise HTTPException(status_code=502, detail="Zammad: ungültiger API-Token.")
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Zammad HTTP {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e




@app.post("/integrations/zammad/tickets")
def create_zammad_ticket(ticket: TicketCreate) -> dict[str, Any]:
    """Erstellt ein neues Ticket in Zammad."""

    if not ZAMMAD_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ZAMMAD_API_TOKEN ist nicht gesetzt.",
        )

    payload = {
        "title": ticket.title,
        "group_id": 1,
        "customer": ticket.customer,
        "article": {
            "subject": ticket.title,
            "body": ticket.description,
            "type": "note",
            "internal": False,
        },
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                f"{ZAMMAD_BASE}/api/v1/tickets",
                headers=_zammad_headers(),
                json=payload,
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=response.status_code,
                detail=response.text,
            )

        return response.json()

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Verbindungsfehler zu Zammad: {str(e)}",
        ) from e