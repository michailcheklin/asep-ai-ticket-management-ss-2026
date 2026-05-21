"""Streamlit-Frontend; BACKEND_URL http://backend_app:8000 in Docker."""
import os
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
ZAMMAD_UI_URL = os.getenv("ZAMMAD_UI_URL", "http://localhost:8080").rstrip("/")

st.set_page_config(page_title="AI Ticket System", layout="wide")
st.title("AI Ticket System")