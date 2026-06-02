from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.services.ai_logic import initialize_ai
from app.config import settings
from app.api.endpoints import router as api_router
from app.db.session import engine, Base
from app.models import all_models  # Import to register models

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables on startup
    Base.metadata.create_all(bind=engine)
    
    # Startup AI logic
    initialize_ai()
    yield
    # Shutdown logic (clean up if any)
    pass


app = FastAPI(title="Legal Assistant API", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API endpoints
app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Backend is running!"}