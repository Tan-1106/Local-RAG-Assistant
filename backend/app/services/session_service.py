import json
from typing                                 import List, Dict
from sqlalchemy.orm                         import Session
from fastapi                                import HTTPException, status
from llama_index.core.chat_engine           import ContextChatEngine
from llama_index.core.retrievers            import AutoMergingRetriever
from llama_index.core.llms                  import ChatMessage as LlamaChatMessage, MessageRole
from app.models.all_models                  import ChatSession, ChatMessage
from app.schemas.session                    import SessionCreate
from app.schemas.chat                       import ChatRequest
from app.repositories.session_repository    import SessionRepository
from app.repositories.message_repository    import MessageRepository
from app.logger                             import get_logger

logger = get_logger(__name__)

class SessionService:
    """
    Service layer handling business logic for chat sessions and conversational messaging.
    """

    @staticmethod
    def create_session(db: Session, user_id: int, session_in: SessionCreate) -> ChatSession:
        """
        Creates a new chat session for a user.

        Args:
            db (Session): The database session.
            user_id (int): The ID of the user requesting session creation.
            session_in (SessionCreate): Payload containing the desired title for the session.

        Returns:
            ChatSession: The newly created ChatSession object.
        """
        session = SessionRepository.create(db, user_id, session_in.title)
        db.commit()
        return session

    @staticmethod
    def list_sessions(db: Session, user_id: int) -> List[ChatSession]:
        """
        Lists all chat sessions belonging to a specific user.

        Args:
            db (Session): The database session.
            user_id (int): The user's ID.

        Returns:
            List[ChatSession]: A list of chat sessions owned by the user.
        """
        return SessionRepository.get_by_user(db, user_id)

    @staticmethod
    def get_session_messages(db: Session, session_id: str, user_id: int) -> List[ChatMessage]:
        """
        Retrieves all messages for a specific chat session, verifying ownership.

        Args:
            db (Session): The database session.
            session_id (str): The ID of the session to fetch messages from.
            user_id (int): The ID of the user attempting to access the messages.

        Returns:
            List[ChatMessage]: A list of all messages in the session.
            
        Raises:
            HTTPException: If the session does not exist or does not belong to the user.
        """
        session = SessionRepository.get_by_id_and_user(db, session_id, user_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found"
            )
        return MessageRepository.get_session_messages(db, session_id)

    @staticmethod
    def delete_session(db: Session, session_id: str, user_id: int) -> Dict[str, str]:
        """
        Deletes a specific chat session, verifying ownership first.

        Args:
            db (Session): The database session.
            session_id (str): The ID of the session to delete.
            user_id (int): The ID of the user attempting the deletion.

        Returns:
            Dict[str, str]: A status and message dictionary indicating success.
            
        Raises:
            HTTPException: If the session does not exist or does not belong to the user.
        """
        session = SessionRepository.get_by_id_and_user(db, session_id, user_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found"
            )
        SessionRepository.delete(db, session)
        return {
            "status": "success",
            "message": f"Successfully deleted session '{session_id}'"
        }

    @staticmethod
    def rename_session(db: Session, session_id: str, user_id: int, new_title: str) -> ChatSession:
        """
        Renames a specific chat session, verifying ownership first.

        Args:
            db (Session): The database session.
            session_id (str): The ID of the session to rename.
            user_id (int): The ID of the user attempting the rename.
            new_title (str): The new title for the session.

        Returns:
            ChatSession: The updated ChatSession object.
            
        Raises:
            HTTPException: If the session does not exist or does not belong to the user.
        """
        session = SessionRepository.get_by_id_and_user(db, session_id, user_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found"
            )
        updated_session = SessionRepository.update_title(db, session, new_title)
        db.commit()
        return updated_session

    @staticmethod
    def process_chat_message(
        db: Session, 
        session_id: str, 
        user_id: int, 
        request: ChatRequest, 
        retriever: AutoMergingRetriever
    ):
        """
        Processes an incoming user chat message, queries the AI engine with context,
        and yields Server-Sent Events (SSE) for token streaming.
        Persists the conversation history after the stream ends.
        """
        # 1. Existence and ownership check
        session = SessionRepository.get_by_id_and_user(db, session_id, user_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found"
            )
            
        # 2. Fetch conversational history (Sliding Window: last 20 messages)
        history = MessageRepository.get_recent_history(db, session_id, limit=20)
        
        try:
            # 3. Call AI query engine passing history context
            llama_history = []
            for msg in history:
                role = MessageRole.USER if msg.role == "user" else MessageRole.ASSISTANT
                llama_history.append(LlamaChatMessage(role=role, content=msg.content))
                
            chat_engine = ContextChatEngine.from_defaults(
                retriever=retriever,
                verbose=True
            )
            
            # Use stream_chat instead of chat
            response = chat_engine.stream_chat(request.question, chat_history=llama_history)
            
            # 4. Stream tokens
            buffer = ""
            for token in response.response_gen:
                buffer += token
                # Yield SSE chunk
                yield f"data: {json.dumps({'chunk': token}, ensure_ascii=False)}\n\n"
            
            # 5. Extract sources
            sources = []
            if hasattr(response, "source_nodes") and response.source_nodes:
                for node in response.source_nodes:
                    sources.append({
                        "score": float(node.score) if node.score else 0.0,
                        "text": node.text,
                        "metadata": node.metadata
                    })
            
            # Yield sources at the end
            yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            
            # 6. Save User and Assistant Message to DB
            answer = buffer.strip()
            MessageRepository.create(db, session_id, "user", request.question)
            sources_json = json.dumps(sources, ensure_ascii=False)
            MessageRepository.create(db, session_id, "assistant", answer, sources_json)
            
            # 7. Auto-generate title using AI if it's currently a default/new title
            if session.title == "Cuộc trò chuyện mới" or not session.title.strip():
                try:
                    from llama_index.core import Settings as LlamaIndexSettings
                    prompt = (
                        "Tạo một tiêu đề ngắn gọn (tối đa 6 từ) bằng Tiếng Việt tóm tắt cho câu hỏi sau. "
                        "Không cần giải thích, chỉ trả về đúng tiêu đề.\n"
                        f"Câu hỏi: {request.question}"
                    )
                    ai_title_response = LlamaIndexSettings.llm.complete(prompt)
                    title_candidate = ai_title_response.text.strip().replace('"', '').replace("'", "")
                    
                    if not title_candidate:
                        title_candidate = " ".join(request.question.split()[:6]) + "..."
                        
                    if len(title_candidate) > 40:
                        title_candidate = title_candidate[:37] + "..."
                        
                    SessionRepository.update_title(db, session, title_candidate)
                except Exception as e:
                    # Fallback to simple title if AI generation fails
                    logger.warning(f"Warning: AI title generation failed: {e}")
                    words = request.question.split()
                    title_candidate = " ".join(words[:6])
                    if len(title_candidate) > 40:
                        title_candidate = title_candidate[:37] + "..."
                    SessionRepository.update_title(db, session, title_candidate)
                
            # Commit all db changes for this round
            db.commit()
            
        except Exception as e:
            logger.error(f"Error processing chat message: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
