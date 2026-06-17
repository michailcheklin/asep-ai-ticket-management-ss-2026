FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    PYTHONPATH=/src

WORKDIR /src

# uv installieren
RUN --mount=type=cache,target=/root/.cache,id=pip  \
    python -m pip install uv

COPY backend/requirements.txt .

RUN --mount=type=cache,target=/root/.cache,id=pip \
    uv pip -v install --system -r ./requirements.txt

COPY . /src
# Hier kommen die Hugging Face-Models rein, die für die Vorab-Überprüfung des Prompts
# zuständig sind
RUN mkdir -p /models



EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
