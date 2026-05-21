"""
dev.py — single entry point for local development
Run with: python dev.py
"""

import os, sys, subprocess, signal, time, webbrowser

os.environ["FAKE_IDP"] = "1"

ROOT = os.path.dirname(os.path.abspath(__file__))

flask_proc = subprocess.Popen(
    [sys.executable, os.path.join(ROOT, "fake_idp.py")],
    env={**os.environ},
)
time.sleep(1)

streamlit_proc = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run",
     os.path.join(ROOT, "app.py"), "--server.headless", "true"],
    env={**os.environ},
)
time.sleep(2)

webbrowser.open("http://localhost:5000/login?next=http://localhost:8501")

def _shutdown(sig, frame):
    flask_proc.terminate()
    streamlit_proc.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

flask_proc.wait()
streamlit_proc.wait()
