from fastapi            import APIRouter
from app.api.auth       import router as auth_router
from app.api.sessions   import router as session_router
from app.api.chat       import router as chat_router
from app.api.documents  import router as documents_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(session_router)
api_router.include_router(chat_router)
api_router.include_router(documents_router)
