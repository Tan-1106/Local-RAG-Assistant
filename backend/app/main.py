import sys
# Reconfigure stdout to support UTF-8 printing (e.g. emojis) on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from fastapi                        import FastAPI, Request
from fastapi.responses              import JSONResponse
from fastapi.middleware.cors        import CORSMiddleware
from contextlib                     import asynccontextmanager
from app.services.ai_logic          import initialize_ai
from app.config                     import settings
from app.api.router                 import api_router
from app.db.session                 import engine, Base, SessionLocal
from sqlalchemy                     import text, inspect
from app.services.admin_bootstrap   import ensure_super_admin
from app.services.request_security  import is_csrf_token_valid, is_origin_allowed
from app.logger                     import get_logger

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
    # Ensure SQLite directory exists
    import os
    if settings.DATABASE_URL.startswith("sqlite"):
        os.makedirs(settings.DATA_DIR, exist_ok=True)

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
        ensure_super_admin(
            db,
            settings.SUPER_ADMIN_USERNAME,
            settings.SUPER_ADMIN_PASSWORD,
        )
    finally:
        db.close()
    
    # Startup AI logic (lazy/non-blocking)
    app.state.index = None
    app.state.retriever = None
    app.state.retriever_version = None
    app.state.ai_initialized = False
    try:
        initialize_ai()
        app.state.ai_initialized = True
    except Exception as e:
        logger.warning(f"Failed to initialize AI stack during startup: {e}")
        logger.info("API is running, but AI features may fail or will lazy-load later.")
    
    yield
    # Shutdown logic (clean up if any)
    pass


app = FastAPI(title="Local RAG Assistant API", lifespan=lifespan)

# Add CORS middleware
allowed_origins_list = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]
allowed_origins = set(allowed_origins_list)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-CSRF-Token"],
)


@app.middleware("http")
async def enforce_browser_request_security(request: Request, call_next):
    """Validate browser origins and double-submit CSRF tokens for cookie auth."""
    if request.url.path.startswith("/api") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if not is_origin_allowed(origin, allowed_origins):
            return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})

        has_auth_cookie = bool(
            request.cookies.get(settings.AUTH_COOKIE_NAME)
            or request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        )
        is_auth_bootstrap = request.url.path in {
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/refresh",
        }
        if has_auth_cookie and not is_auth_bootstrap:
            csrf_cookie = request.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
            csrf_header = request.headers.get("X-CSRF-Token")
            if not is_csrf_token_valid(csrf_cookie, csrf_header):
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})

    return await call_next(request)


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
