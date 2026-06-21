"""
Script that starts the frontend alongside Flask in the backgroud for the login
"""

import os
import sys
import subprocess
import signal
import time
import webbrowser

from fake_idp import IDP_PORT

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

webbrowser.open(f"http://localhost:{IDP_PORT}/login?next=http://localhost:8501")

def _shutdown(sig, frame):
    """Terminate all subprocesses when termination signal is received"""
    flask_proc.terminate()
    streamlit_proc.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

flask_proc.wait()
streamlit_proc.wait()
