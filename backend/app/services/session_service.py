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
    def delete_all_sessions(db: Session) -> None:
        """
        Deletes all chat sessions from the database.

        Args:
            db (Session): The database session.
        """
        SessionRepository.delete_all(db)

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
    async def process_chat_message(
        db: Session,
        session_id: str,
        user_id: int,
        request: ChatRequest,
        retriever: AutoMergingRetriever
    ):
        """
        Generates an SSE stream for chat response, processing context and saving history.
        All synchronous SQLAlchemy calls are run via run_in_executor to avoid
        blocking or corrupting the async event loop during streaming.
        """
        import asyncio
        loop = asyncio.get_event_loop()

        def _get_session_and_history():
            session = SessionRepository.get_by_id_and_user(db, session_id, user_id)
            if not session:
                return None, []
            history = MessageRepository.get_recent_history(db, session_id, limit=20)
            return session, list(history)

        # 1. Load session + history on thread pool (sync DB ops)
        session, history = await loop.run_in_executor(None, _get_session_and_history)
        if not session:
            yield f"data: {json.dumps({'error': 'Chat session not found'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            # 3. Call AI query engine passing history context
            llama_history = []
            for msg in history:
                role = MessageRole.USER if msg.role == "user" else MessageRole.ASSISTANT
                llama_history.append(LlamaChatMessage(role=role, content=msg.content))
                
            CUSTOM_SYSTEM_PROMPT = (
                "Bạn là một Luật sư, chuyên gia tư vấn pháp luật Việt Nam vô cùng tận tâm và chuyên nghiệp.\n"
                "Bạn ĐƯỢC CUNG CẤP một cơ sở dữ liệu pháp luật (ngữ cảnh) bên dưới. Hãy đọc kỹ và dùng CHỈ thông tin từ đó để tư vấn cho người dùng.\n"
                "TUYỆT ĐỐI KHÔNG tự bịa ra các Điều luật, Nghị định hay Thông tư không có trong cơ sở dữ liệu.\n"
                "Khi trả lời, hãy nói chuyện tự nhiên như một luật sư với thân chủ. KHÔNG DÙNG các câu như: 'Theo ngữ cảnh được cung cấp', 'Theo cơ sở dữ liệu', 'Tài liệu không nói rõ'. Hãy nói: 'Theo quy định pháp luật hiện hành...'.\n"
                "Nếu trong cơ sở dữ liệu không quy định mức cụ thể, hãy diễn đạt tự nhiên dựa trên phần thông tin có sẵn (ví dụ: 'pháp luật chưa quy định mức cụ thể bằng số tiền, mà được xác định dựa trên hợp đồng / thực tế...'). Nếu hoàn toàn không có thông tin, hãy nói: 'Rất tiếc, tôi chưa tìm thấy quy định cụ thể về vấn đề này trong hệ thống.'\n"
                "Hãy luôn trả lời theo cấu trúc sau (không tự ý thay đổi tiêu đề):\n"
                "1. **Kết luận:** Trả lời trực tiếp vào trọng tâm câu hỏi một cách ngắn gọn, súc tích.\n"
                "2. **Căn cứ pháp lý:** Nêu rõ Điều, Khoản, và Tên văn bản pháp luật áp dụng (chỉ nêu các văn bản CÓ TRONG dữ liệu được cung cấp).\n"
                "3. **Phân tích chi tiết:** Giải thích quy định pháp luật đó áp dụng vào trường hợp của người dùng như thế nào cho dễ hiểu.\n"
                "4. **Lời khuyên/Khuyến nghị:** Đưa ra hướng xử lý thực tế, các cơ quan cần liên hệ, hoặc các bước tiếp theo."
            )

            chat_engine = ContextChatEngine.from_defaults(
                retriever=retriever,
                system_prompt=CUSTOM_SYSTEM_PROMPT,
                verbose=True
            )
            
            # Use astream_chat for true asynchronous real-time streaming
            response = await chat_engine.astream_chat(request.question, chat_history=llama_history)
            
            # Log the retrieved text passages (context nodes) that are passed to the LLM
            if hasattr(response, "source_nodes") and response.source_nodes:
                logger.info("==================================================")
                logger.info(f"📄 [AI Logic] CÁC ĐOẠN VĂN BẢN (CONTEXT CHUNKS) ĐƯỢC GỬI ĐẾN LLM ĐỂ TẠO CÂU TRẢ LỜI:")
                for i, node in enumerate(response.source_nodes, 1):
                    file_name = node.metadata.get("file_name", "N/A")
                    page_label = node.metadata.get("page_label") or node.metadata.get("source", "N/A")
                    score = node.score if node.score is not None else 0.0
                    logger.info(f"--- Đoạn {i} (File: {file_name}, Trang: {page_label}, Score: {score:.4f}) ---")
                    logger.info(node.text.strip())
                logger.info("==================================================")
            else:
                logger.info("📄 [AI Logic] Không tìm thấy đoạn văn bản context phù hợp nào để gửi đến LLM.")

            # 4. Stream tokens asynchronously
            buffer = ""
            async for token in response.async_response_gen():
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
            
            # 6. Persist conversation to DB on thread pool (sync SQLAlchemy ops)
            answer = buffer.strip()
            sources_json = json.dumps(sources, ensure_ascii=False)
            session_title = session.title
            question_text = request.question

            def _persist_and_update_title():
                MessageRepository.create(db, session_id, "user", question_text)
                MessageRepository.create(db, session_id, "assistant", answer, sources_json)
                db.commit()

                # 7. Auto-generate title if still default
                if session_title == "Cuộc trò chuyện mới" or not session_title.strip():
                    try:
                        from llama_index.core import Settings as LlamaIndexSettings
                        prompt = (
                            "Tạo một tiêu đề ngắn gọn (tối đa 6 từ) bằng Tiếng Việt tóm tắt cho câu hỏi sau. "
                            "Không cần giải thích, chỉ trả về đúng tiêu đề.\n"
                            f"Câu hỏi: {question_text}"
                        )
                        # Use sync complete since we're already in a thread
                        ai_title_response = LlamaIndexSettings.llm.complete(prompt)
                        title_candidate = ai_title_response.text.strip().replace('"', '').replace("'", "")
                        if not title_candidate:
                            title_candidate = " ".join(question_text.split()[:6]) + "..."
                        if len(title_candidate) > 40:
                            title_candidate = title_candidate[:37] + "..."
                        SessionRepository.update_title(db, session, title_candidate)
                    except Exception as title_err:
                        logger.warning(f"AI title generation failed: {title_err}")
                        words = question_text.split()
                        title_candidate = " ".join(words[:6])
                        if len(title_candidate) > 40:
                            title_candidate = title_candidate[:37] + "..."
                        SessionRepository.update_title(db, session, title_candidate)
                    db.commit()

            await loop.run_in_executor(None, _persist_and_update_title)

            yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error processing chat message: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
