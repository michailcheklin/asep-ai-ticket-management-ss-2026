"""Streamlit-Frontend; BACKEND_URL http://backend_app:8000 in Docker."""
import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
ZAMMAD_UI_URL = os.getenv("ZAMMAD_UI_URL", "http://localhost:8080").rstrip("/")

st.set_page_config(page_title="AI Ticket System", layout="wide")
st.title("AI Ticket System")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Backend")
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=5)
        r.raise_for_status()
        st.success(f"Verbunden: {r.json()}")
    except Exception as e:
        st.error(f"Nicht erreichbar ({BACKEND_URL}): {e}")

with col2:
    st.subheader("Zammad")
    st.link_button("Zammad Web-Oberfläche öffnen", ZAMMAD_UI_URL, use_container_width=True)
    try:
        zr = requests.get(f"{BACKEND_URL}/integrations/zammad/status", timeout=8)
        zr.raise_for_status()
        zs = zr.json()
        if zs.get("api_ok"):
            st.success(f"API verbunden als {zs.get('user', {}).get('login', '?')}")
        elif zs.get("reachable"):
            st.warning(zs.get("detail") or "Zammad erreichbar; Token prüfen.")
        else:
            st.error(zs.get("detail") or "Zammad nicht erreichbar (URL/Stack prüfen).")
    except Exception as e:
        st.error(f"Status nicht abrufbar: {e}")

st.caption("Backend: `backend/main.py` · Tickets-API: `GET /integrations/zammad/tickets` (mit Token).")

st.divider()

st.header("Tickets")

try:
    ticket_response = requests.get(
        f"{BACKEND_URL}/integrations/zammad/tickets",
        timeout=10,
    )
    ticket_response.raise_for_status()
    tickets = ticket_response.json()
    if not tickets:
        st.info("Keine Tickets gefunden.")
    else:
        for ticket in tickets:
            with st.container(border=True):
                st.subheader(f"#{ticket.get('number')} - {ticket.get('title')} - {ticket.get('description')}")

                st.write(f"**ID:** {ticket.get('id')}")
                st.write(f"**Status:** {ticket.get('state_id')}")
                st.write(f"**Priorität:** {ticket.get('priority_id')}")
                st.write(f"**Erstellt:** {ticket.get('created_at')}")

except Exception as e:
    st.error(f"Tickets konnten nicht geladen werden: {e}")
