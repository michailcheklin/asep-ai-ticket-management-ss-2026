FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    FAKE_IDP=1 \
    PYTHONPATH=/src

WORKDIR /src

# uv installieren
RUN --mount=type=cache,target=/root/.cache,id=pip \
    python -m pip install uv

COPY frontend/requirements.txt .
RUN --mount=type=cache,target=/root/.cache,id=pip \
    uv pip -v install --system -r ./requirements.txt
COPY . /src

# 8501 = Streamlit app
# 5000 = fake IdP login page
EXPOSE 8501 5000

CMD ["python", "./frontend/dev.py"]
