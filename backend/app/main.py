from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.ai_logic import initialize_ai

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs when the server starts up
    initialize_ai()
    yield
    # Runs when the server shuts down
    print("🛑 Server is shutting down...")

app = FastAPI(title="Legal Assistant API", lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Backend RAG is running!"}