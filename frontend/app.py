"""Live Streamlit frontend connected to the AI backend."""
from clients.live_client import LiveChatClient
from ui.chat import run_app

run_app(LiveChatClient())
