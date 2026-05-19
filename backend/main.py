from fastapi import FastAPI

app = FastAPI(
    title="AI Ticket Backend",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "message": "AI Ticket Management Backend läuft"
    }


@app.get("/status")
def status():
    return {
        "status": "online"
    }


@app.get("/health")
def health():
    return {
        "healthy": True
    }