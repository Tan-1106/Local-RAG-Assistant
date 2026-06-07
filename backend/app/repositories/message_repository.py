from typing                 import List, Optional
from sqlalchemy.orm         import Session
from app.models.all_models  import ChatMessage

class MessageRepository:
    """
    Repository for managing ChatMessage database operations.
    """

    @staticmethod
    def get_session_messages(db: Session, session_id: str) -> List[ChatMessage]:
        """
        Retrieves all messages for a given chat session, ordered chronologically.

        Args:
            db (Session): The database session.
            session_id (str): The ID of the chat session.

        Returns:
            List[ChatMessage]: A list of all messages in the session.
        """
        return db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at.asc()).all()

    @staticmethod
    def get_recent_history(db: Session, session_id: str, limit: int = 20) -> List[ChatMessage]:
        """
        Retrieves the most recent messages for a chat session (Sliding Window),
        ordered chronologically.

        Args:
            db (Session): The database session.
            session_id (str): The ID of the chat session.
            limit (int): The maximum number of recent messages to retrieve (default: 20).

        Returns:
            List[ChatMessage]: A list of the recent messages in the session, chronologically ordered.
        """
        # Sliding Window logic
        history_desc = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
        # Reverse to pass them chronologically to the engine
        return history_desc[::-1]

    @staticmethod
    def create(db: Session, session_id: str, role: str, content: str, sources: Optional[str] = None) -> ChatMessage:
        """
        Creates a new chat message and saves it to the database.

        Args:
            db (Session): The database session.
            session_id (str): The ID of the chat session this message belongs to.
            role (str): The role of the sender (e.g., 'user' or 'assistant').
            content (str): The textual content of the message.
            sources (Optional[str]): Serialized JSON string of sources if applicable.

        Returns:
            ChatMessage: The newly created chat message object.
        """
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            sources=sources
        )
        db.add(message)
        db.flush()
        db.refresh(message)
        return message
