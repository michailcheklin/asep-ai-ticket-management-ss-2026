"""
Script that starts the frontend alongside Flask in the backgroud for the login
"""

import os
import sys
import subprocess
import signal
import time
import webbrowser

os.environ["FAKE_IDP"] = "1"

ROOT = os.path.dirname(os.path.abspath(__file__))

flask_proc = subprocess.Popen(
    [sys.executable, os.path.join(ROOT, "fake_idp.py")],
    env={**os.environ},
) # nosec B603
# "nosec B603" tells teamscale that the security issues that may arise by using 
# a subprocess ahve been reviewed and do not represent a security threat since it
# does not take any user inputs.
time.sleep(1)

streamlit_proc = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run",
     os.path.join(ROOT, "app.py"), "--server.headless", "true"],
    env={**os.environ},
) # nosec B603
time.sleep(2)

webbrowser.open("http://localhost:5000/login?next=http://localhost:8501")

"""
Terminate all subprocesses when termination signal is received
""" 
def _shutdown(sig, frame):
    flask_proc.terminate()
    streamlit_proc.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

flask_proc.wait()
streamlit_proc.wait()
