from typing                         import List
from sqlalchemy.orm                 import Session
from llama_index.core.retrievers    import AutoMergingRetriever
from fastapi                        import APIRouter, Depends, status
from fastapi.responses              import StreamingResponse
from app.db.session                 import get_db
from app.models.all_models          import User
from app.schemas.session            import SessionCreate, SessionResponse, MessageResponse, SessionUpdate
from app.schemas.chat               import ChatRequest
from app.services.auth_service      import get_current_user
from app.services.session_service   import SessionService
from app.services.chat_engine       import get_retriever


router = APIRouter(prefix="/sessions", tags=["Chat Sessions"])


@router.post("/", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    session_in: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new chat session for the authenticated user.

    Args:
        session_in (SessionCreate): Payload containing the session title.
        db (Session, optional): The database session dependency.
        current_user (User, optional): The authenticated user dependency.

    Returns:
        SessionResponse: The created session details.
    """
    return SessionService.create_session(db, current_user.id, session_in)


@router.get("/", response_model=List[SessionResponse])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all chat sessions belonging to the current user, ordered by creation date.

    Args:
        db (Session, optional): The database session dependency.
        current_user (User, optional): The authenticated user dependency.

    Returns:
        List[SessionResponse]: A list of the user's chat sessions.
    """
    return SessionService.list_sessions(db, current_user.id)


@router.get("/{session_id}/messages", response_model=List[MessageResponse])
def get_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve all chat message history for a specific session, verified by ownership.

    Args:
        session_id (str): The ID of the session.
        db (Session, optional): The database session dependency.
        current_user (User, optional): The authenticated user dependency.

    Returns:
        List[MessageResponse]: A list of all messages in the session.
    """
    return SessionService.get_session_messages(db, session_id, current_user.id)


@router.delete("/{session_id}", status_code=status.HTTP_200_OK)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a chat session and all its associated messages, verified by ownership.

    Args:
        session_id (str): The ID of the session to delete.
        db (Session, optional): The database session dependency.
        current_user (User, optional): The authenticated user dependency.

    Returns:
        dict: A status dict confirming deletion.
    """
    return SessionService.delete_session(db, session_id, current_user.id)


@router.patch("/{session_id}/title", response_model=SessionResponse, status_code=status.HTTP_200_OK)
def rename_session(
    session_id: str,
    session_update: SessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Rename a chat session, verified by ownership.

    Args:
        session_id (str): The ID of the session to rename.
        session_update (SessionUpdate): The payload containing the new title.
        db (Session, optional): The database session dependency.
        current_user (User, optional): The authenticated user dependency.

    Returns:
        SessionResponse: The updated session details.
    """
    return SessionService.rename_session(db, session_id, current_user.id, session_update.title)


@router.post("/{session_id}/chat")
def session_chat_endpoint(
    session_id: str,
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    retriever: AutoMergingRetriever = Depends(get_retriever)
):
    """
    Process a chat message within a session.
    Loads past conversation history, queries stateful ContextChatEngine,
    and returns a Server-Sent Events (SSE) stream.
    Saves conversation logs to DB after the stream ends.

    Args:
        session_id (str): The ID of the session.
        request (ChatRequest): The chat request containing the user's question.
        db (Session, optional): The database session dependency.
        current_user (User, optional): The authenticated user dependency.
        retriever (AutoMergingRetriever, optional): The global AI stateless retriever dependency.

    Returns:
        StreamingResponse: An SSE text/event-stream.
    """
    return StreamingResponse(
        SessionService.process_chat_message(
            db=db,
            session_id=session_id,
            user_id=current_user.id,
            request=request,
            retriever=retriever
        ),
        media_type="text/event-stream"
    )
