import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.all_models import ChatSession, ChatMessage, User
from app.schemas.session import SessionCreate, SessionResponse, MessageResponse
from app.schemas.chat import ChatRequest, ChatResponse, SourceNode
from app.services.auth_service import get_current_user
from app.services.chat_engine import answer_legal_question


router = APIRouter(prefix="/sessions", tags=["Chat Sessions"])


@router.post("/", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    session_in: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new chat session for the authenticated user."""
    session = ChatSession(
        user_id=current_user.id,
        title=session_in.title
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/", response_model=List[SessionResponse])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all chat sessions belonging to the current user, ordered by creation date."""
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )
    return sessions


@router.get("/{session_id}/messages", response_model=List[MessageResponse])
def get_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve all chat message history for a specific session, verified by ownership."""
    # Ownership and existence check
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return messages


@router.delete("/{session_id}", status_code=status.HTTP_200_OK)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a chat session and all its associated messages, verified by ownership."""
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    db.delete(session)
    db.commit()
    return {
        "status": "success",
        "message": f"Successfully deleted session '{session_id}'"
    }


@router.post("/{session_id}/chat", response_model=ChatResponse)
def session_chat_endpoint(
    session_id: str,
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Process a chat message within a session.
    Loads past conversation history, queries stateful ContextChatEngine,
    saves conversation logs to DB, and auto-updates the session title if needed.
    """
    # 1. Existence and ownership check
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
        
    # 2. Fetch conversational history (ordered chronologically)
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    
    try:
        # 3. Call AI query engine passing history context
        result = answer_legal_question(request.question, history)
        
        # 4. Save User Message to DB
        user_message = ChatMessage(
            session_id=session_id,
            role="user",
            content=request.question
        )
        db.add(user_message)
        
        # 5. Save Assistant Message (with sources serialized to JSON string) to DB
        sources_json = json.dumps(result["sources"])
        assistant_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=result["answer"],
            sources=sources_json
        )
        db.add(assistant_message)
        
        # 6. Auto-generate title if it's currently a default/new title
        if session.title == "Cuộc trò chuyện mới" or not session.title.strip():
            # Extract first 6 words of user question (max 40 chars) as title
            words = request.question.split()
            title_candidate = " ".join(words[:6])
            if len(title_candidate) > 40:
                title_candidate = title_candidate[:37] + "..."
            session.title = title_candidate
            
        db.commit()
        db.refresh(session)
        
        # 7. Map to Pydantic ChatResponse
        sources_response = [
            SourceNode(
                score=source["score"],
                text=source["text"],
                metadata=source["metadata"]
            )
            for source in result["sources"]
        ]
        
        return ChatResponse(
            answer=result["answer"],
            sources=sources_response
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

