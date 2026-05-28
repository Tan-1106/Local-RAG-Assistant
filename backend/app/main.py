from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.ai_logic import initialize_ai

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    initialize_ai()
    yield
    # Shutdown logic (clean up if any)
    pass

app = FastAPI(title="Legal Assistant API", lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Backend is running!"}