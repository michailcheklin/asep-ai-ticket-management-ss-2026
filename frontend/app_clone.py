"""Mock Streamlit frontend clone for UI testing without backend or AI calls."""
from clients.mock_client import MockChatClient
from ui.chat import run_app

run_app(MockChatClient(), mock_mode=True)
