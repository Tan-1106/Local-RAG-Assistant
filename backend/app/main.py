import sys
# Reconfigure stdout to support UTF-8 printing (e.g. emojis) on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from fastapi                    import FastAPI
from fastapi.middleware.cors    import CORSMiddleware
from contextlib                 import asynccontextmanager
from app.services.ai_logic      import initialize_ai
from app.config                 import settings
from app.api.router             import api_router
from app.db.session             import engine, Base, SessionLocal
from sqlalchemy                 import text, inspect
from app.models.all_models      import User
from app.services.auth_service  import get_password_hash
from app.logger                 import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Handles startup events (DB creation, AI initialization) and shutdown events.

    Args:
        app (FastAPI): The FastAPI application instance.
        
    Yields:
        None
    """
    # Create DB tables on startup
    Base.metadata.create_all(bind=engine)

    # Migrate table to add role if missing
    inspector = inspect(engine)
    if inspector.has_table("users"):
        columns = [col["name"] for col in inspector.get_columns("users")]
        if "role" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'user'"))
                conn.commit()

    # Initialize Super Admin user
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.username == settings.SUPER_ADMIN_USERNAME).first()
        if not admin_user:
            admin_user = User(
                username=settings.SUPER_ADMIN_USERNAME,
                hashed_password=get_password_hash(settings.SUPER_ADMIN_PASSWORD),
                role="admin"
            )
            db.add(admin_user)
            db.commit()
        elif admin_user.role != "admin":
            admin_user.role = "admin"
            db.commit()
    finally:
        db.close()
    
    # Startup AI logic (lazy/non-blocking)
    app.state.index = None
    app.state.ai_initialized = False
    try:
        initialize_ai()
        app.state.ai_initialized = True
        # We don't initialize chat_engine here anymore, but we can set up the index in rag_pipeline
    except Exception as e:
        logger.warning(f"Failed to initialize AI stack during startup: {e}")
        logger.info("API is running, but AI features may fail or will lazy-load later.")
    
    yield
    # Shutdown logic (clean up if any)
    pass


app = FastAPI(title="Legal Assistant API", lifespan=lifespan)

# Add CORS middleware
allowed_origins_list = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API endpoints
app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    """
    Health check endpoint for the backend API.

    Returns:
        dict: A status dictionary confirming the backend is running.
    """
    return {"status": "ok", "message": "Backend is running!"}
