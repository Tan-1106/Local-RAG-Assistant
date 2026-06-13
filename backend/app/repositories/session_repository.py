from typing                 import List, Optional
from sqlalchemy.orm         import Session
from app.models.all_models  import ChatSession

class SessionRepository:
    """
    Repository for managing ChatSession database operations.
    """

    @staticmethod
    def get_by_id_and_user(db: Session, session_id: str, user_id: int) -> Optional[ChatSession]:
        """
        Retrieves a specific chat session belonging to a user.

        Args:
            db (Session): The database session.
            session_id (str): The unique identifier of the session.
            user_id (int): The ID of the user who owns the session.

        Returns:
            Optional[ChatSession]: The chat session if found and owned by the user, otherwise None.
        """
        return db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id
        ).first()

    @staticmethod
    def get_by_user(db: Session, user_id: int) -> List[ChatSession]:
        """
        Retrieves all chat sessions for a specific user, ordered by creation date descending.

        Args:
            db (Session): The database session.
            user_id (int): The user's ID.

        Returns:
            List[ChatSession]: A list of the user's chat sessions.
        """
        return db.query(ChatSession).filter(
            ChatSession.user_id == user_id
        ).order_by(ChatSession.created_at.desc()).all()

    @staticmethod
    def create(db: Session, user_id: int, title: str) -> ChatSession:
        """
        Creates a new chat session for a user.

        Args:
            db (Session): The database session.
            user_id (int): The ID of the user creating the session.
            title (str): The title of the session.

        Returns:
            ChatSession: The newly created chat session.
        """
        session = ChatSession(
            user_id=user_id,
            title=title
        )
        db.add(session)
        db.flush()
        db.refresh(session)
        return session

    @staticmethod
    def delete_all(db: Session):
        """
        Deletes all chat sessions and their associated messages from the database.

        Args:
            db (Session): The database session.
        """
        # Delete messages first (if cascade is not strictly enforced by SQLite pragmas)
        from app.models.all_models import ChatMessage
        db.query(ChatMessage).delete()
        db.query(ChatSession).delete()
        db.commit()

    @staticmethod
    def update_title(db: Session, session: ChatSession, new_title: str) -> ChatSession:
        """
        Updates the title of an existing chat session.

        Args:
            db (Session): The database session.
            session (ChatSession): The session object to update.
            new_title (str): The new title to assign.

        Returns:
            ChatSession: The updated chat session object.
        """
        session.title = new_title
        db.flush()
        db.refresh(session)
        return session

    @staticmethod
    def delete(db: Session, session: ChatSession) -> None:
        """
        Deletes a chat session from the database.

        Args:
            db (Session): The database session.
            session (ChatSession): The chat session object to delete.
        """
        db.delete(session)
        db.commit()
