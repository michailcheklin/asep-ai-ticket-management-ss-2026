FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models

WORKDIR /app

# uv installieren
RUN --mount=type=cache,target=/root/.cache,id=pip  \
    python -m pip install uv

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache,id=pip \
    uv pip -v install --system -r requirements.txt

# Hier kommen die Hugging Face-Models rein, die für die Vorab-Überprüfung des Prompts
# zuständig sind
RUN mkdir -p /models

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
