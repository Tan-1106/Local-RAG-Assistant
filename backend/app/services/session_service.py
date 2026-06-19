import json
from typing                                 import List, Dict
from sqlalchemy.orm                         import Session
from fastapi                                import HTTPException, status
from llama_index.core.retrievers            import AutoMergingRetriever
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
            # 3. Retrieve source nodes manually to inject IDs
            source_nodes = await retriever.aretrieve(request.question)
            
            context_str = ""
            for i, node in enumerate(source_nodes, 1):
                file_name = node.metadata.get("file_name", "Tài liệu")
                context_str += f"\n[SYS:{i}] {file_name}\n{node.text.strip()}\n"

            CUSTOM_SYSTEM_PROMPT = f"""Bạn là một trợ lý AI chuyên tư vấn pháp luật Việt Nam. Hành xử như một luật sư tận tâm, chuyên nghiệp.
            
            ## QUY TẮC TUYỆT ĐỐI
            - Chỉ sử dụng thông tin có trong CƠ SỞ DỮ LIỆU bên dưới. Không bịa đặt điều luật, nghị định, hay thông tư không có trong đó.
            - Nói chuyện tự nhiên như luật sư với thân chủ. Không dùng cụm: "Theo ngữ cảnh được cung cấp", "Theo tài liệu", "Cơ sở dữ liệu không đề cập". Hãy nói: "Theo quy định pháp luật hiện hành...".
            - Ký hiệu [SYS:N] trong cơ sở dữ liệu là mã nội bộ của hệ thống để theo dõi nguồn. TUYỆT ĐỐI KHÔNG nhắc đến [SYS:N], "Nguồn", hay bất kỳ số thứ tự nào trong câu trả lời.

            ## PHÂN LOẠI CÂU HỎI VÀ CÁCH XỬ LÝ

            ### Loại 1: Chào hỏi / Hỏi về bản thân trợ lý
            Ví dụ: "Xin chào", "Bạn là ai?", "Bạn có thể làm gì?"
            → Trả lời bằng văn bản thường, tự nhiên, ngắn gọn. KHÔNG nhắc đến bất kỳ tài liệu hay văn bản pháp luật nào.
            → KHÔNG dùng JSON.

            ### Loại 2: Câu hỏi ngoài phạm vi pháp luật
            Ví dụ: Nấu ăn, toán học, lập trình, giải trí, thể thao, y tế, v.v.
            → Từ chối DỨT KHOÁT, lịch sự bằng văn bản thường. Chỉ nói rõ bạn chỉ hỗ trợ pháp luật Việt Nam.
            → KHÔNG được gợi ý, đề nghị hỗ trợ thêm, hay trả lời "một phần" nội dung ngoài lề dù người dùng có hỏi thêm nhiều lần.
            → KHÔNG dùng JSON.

            ### Loại 3: Câu hỏi pháp lý
            → Trả về JSON theo đúng định dạng sau. KHÔNG thêm bất kỳ văn bản nào bên ngoài JSON.

            ```json
            {{
            "answer": "<nội dung câu trả lời>",
            "used_sources": [<danh sách số N từ các [SYS:N] mà bạn đã sử dụng>]
            }}
            ```

            #### Quy tắc viết "answer":
            - Trích dẫn bằng cách nêu tên điều khoản và tên văn bản pháp luật tự nhiên trong câu. Ví dụ: "Theo Điều 7 Thông tư 23/2026/TT-BTC, mức chi là 500.000 đồng/ngày công."
            - TUYỆT ĐỐI KHÔNG viết [SYS:N], [1], [2], "Nguồn 1", "Nguồn [N]", hay bất kỳ số thứ tự nào trong câu trả lời.
            - KHÔNG đề cập số trang hay vị trí vật lý của tài liệu.
            - Nếu không có thông tin trong cơ sở dữ liệu, trả lời: "Rất tiếc, tôi chưa tìm thấy quy định cụ thể về vấn đề này trong hệ thống."

            #### Quy tắc điền "used_sources":
            - Liệt kê các số N (số nguyên) từ [SYS:N] của các đoạn bạn thực sự đã dùng để trả lời.
            - Ví dụ: nếu dùng [SYS:1] và [SYS:3], điền [1, 3].
            - Nếu không dùng nguồn nào, điền [].

            ---

            === CƠ SỞ DỮ LIỆU PHÁP LUẬT ===
            {context_str}"""
            

            from llama_index.core.base.llms.types import ChatMessage, MessageRole
            from app.services.ai_logic import LlamaIndexSettings
            import re

            messages = [ChatMessage(role=MessageRole.SYSTEM, content=CUSTOM_SYSTEM_PROMPT)]
            for msg in history:
                role = MessageRole.USER if msg.role == "user" else MessageRole.ASSISTANT
                # We need to ensure history doesn't break the JSON format constraint, but history is just text.
                messages.append(ChatMessage(role=role, content=msg.content))
            messages.append(ChatMessage(role=MessageRole.USER, content=request.question))

            # Log the retrieved text passages
            if source_nodes:
                logger.info("==================================================")
                logger.info(f"📄 [AI Logic] CÁC ĐOẠN VĂN BẢN (CONTEXT CHUNKS) ĐƯỢC GỬI ĐẾN LLM ĐỂ TẠO CÂU TRẢ LỜI:")
                for i, node in enumerate(source_nodes, 1):
                    file_name = node.metadata.get("file_name", "N/A")
                    page_label = node.metadata.get("page_label") or node.metadata.get("source", "N/A")
                    score = node.score if node.score is not None else 0.0
                    logger.info(f"--- Nguồn {i} (File: {file_name}, Trang: {page_label}, Score: {score:.4f}) ---")
                    logger.info(node.text.strip())
                logger.info("==================================================")
            else:
                logger.info("📄 [AI Logic] Không tìm thấy đoạn văn bản context phù hợp nào để gửi đến LLM.")

            # 4. Stream tokens asynchronously
            # Use json_mode LLM for legal Q&A (has sources), plain LLM for greetings/off-topic
            active_llm = getattr(LlamaIndexSettings, 'chat_llm', LlamaIndexSettings.llm) if source_nodes else LlamaIndexSettings.llm
            response_gen = await active_llm.astream_chat(messages)
            
            accumulated_json = ""
            extracted_answer = ""

            # Regex for complete [SYS:N] tags
            _SYS_COMPLETE_RE = re.compile(r'\[SYS:\d+\]')
            # Regex matching any string that is a valid *prefix* of [SYS:N] (e.g. "[", "[S", "[SYS:", "[SYS:1")
            _SYS_PARTIAL_RE = re.compile(r'\[(?:S(?:Y(?:S(?::\d*)?)?)?)?$')

            def get_logical_response(jstr: str) -> str:
                """Extract the raw answer text from (possibly partial) JSON. No SYS stripping here."""
                match = re.search(r'(.*?)(?:```(?:json)?\s*)?\{[\s\n]*"answer"\s*:\s*"(.*)', jstr, re.DOTALL)
                if match:
                    preamble = match.group(1).lstrip()
                    val = match.group(2)
                    res = ""
                    i = 0
                    while i < len(val):
                        if val[i] == '\\':
                            if i + 1 < len(val):
                                if val[i+1] == 'n': res += '\n'
                                elif val[i+1] == '"': res += '"'
                                elif val[i+1] == '\\': res += '\\'
                                elif val[i+1] == 't': res += '\t'
                                else: res += val[i+1]
                                i += 2
                            else:
                                break # incomplete escape
                        elif val[i] == '"':
                            break # end of string
                        else:
                            res += val[i]
                            i += 1

                    if preamble:
                        return preamble + "\n\n" + res
                    return res

                match_potential_json = re.search(r'(.*?)(?:```(?:json)?\s*|\{)', jstr, re.DOTALL)
                if match_potential_json:
                    return match_potential_json.group(1).lstrip()

                return jstr.lstrip()

            def emit_safe(buf: str) -> tuple[str, str]:
                """
                Given a buffer of extracted answer text, strip complete [SYS:N] tags,
                then split into (safe_to_emit, hold_back).
                'hold_back' is any suffix that looks like it might be the start of a [SYS:...] tag.
                """
                # Strip all complete tags
                cleaned = _SYS_COMPLETE_RE.sub('', buf)
                # Hold back any partial tag prefix at the very end
                m = _SYS_PARTIAL_RE.search(cleaned)
                if m:
                    return cleaned[:m.start()], cleaned[m.start():]
                return cleaned, ''

            # raw_extracted: un-stripped answer text, used only for tracking how much we've parsed
            raw_extracted = ""
            # pending_buf: characters waiting to be safely emitted (may contain partial SYS tags)
            pending_buf = ""

            async for chunk in response_gen:
                token = chunk.delta
                if token:
                    accumulated_json += token
                    new_raw = get_logical_response(accumulated_json)
                    if len(new_raw) > len(raw_extracted):
                        pending_buf += new_raw[len(raw_extracted):]
                        raw_extracted = new_raw

                    safe, pending_buf = emit_safe(pending_buf)
                    if safe:
                        extracted_answer += safe
                        yield f"data: {json.dumps({'chunk': safe}, ensure_ascii=False)}\n\n"

            # Flush pending buffer at end of stream — strip any remnant partial tag
            if pending_buf:
                final_buf = _SYS_COMPLETE_RE.sub('', pending_buf)
                final_buf = _SYS_PARTIAL_RE.sub('', final_buf)  # strip any unfinished tag
                if final_buf:
                    extracted_answer += final_buf
                    yield f"data: {json.dumps({'chunk': final_buf}, ensure_ascii=False)}\n\n"

            # Stream finished, save the parsed answer
            final_answer = extracted_answer if extracted_answer else accumulated_json.strip()

            # Flush any remaining buffer if it was a plain text response that just happened to contain a `{`
            if '"answer"' not in accumulated_json:
                # Plain text response (greetings, off-topic) — strip any SYS tags and emit remainder
                plain = _SYS_COMPLETE_RE.sub('', accumulated_json.strip())
                plain = _SYS_PARTIAL_RE.sub('', plain)
                final_answer = plain
                if len(final_answer) > len(extracted_answer):
                    delta = final_answer[len(extracted_answer):]
                    yield f"data: {json.dumps({'chunk': delta}, ensure_ascii=False)}\n\n"

            # Safety net: strip any leaked SYS tags from the final saved answer
            final_answer = _SYS_COMPLETE_RE.sub('', final_answer)
            final_answer = _SYS_PARTIAL_RE.sub('', final_answer)

            # 5. Extract used_sources and filter
            used_sources = []
            try:
                clean_json = accumulated_json.strip()
                if not clean_json:
                    raise ValueError("Empty response from model")
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]

                final_data = json.loads(clean_json.strip(), strict=False)
                used_sources = final_data.get("used_sources", [])
                if not isinstance(used_sources, list):
                    used_sources = []
            except Exception as e:
                logger.warning(f"Could not parse JSON from LLM response: {e}. Falling back to source extraction.")
                import re
                match = re.search(r'"used_sources"\s*:\s*\[(.*?)\]', accumulated_json, re.DOTALL)
                if match:
                    numbers_str = match.group(1)
                    used_sources = [int(n.strip()) for n in numbers_str.split(',') if n.strip().isdigit()]
                elif final_answer and source_nodes:
                    # Model answered using retrieved context but didn't return JSON format.
                    # Show all retrieved sources — better to show all than none.
                    used_sources = list(range(1, len(source_nodes) + 1))
                    logger.warning(f"LLM ignored JSON format. Showing all {len(source_nodes)} retrieved sources as fallback.")

            seen_sources = set()
            filtered_sources = []
            
            for i, node in enumerate(source_nodes, 1):
                if i in used_sources or str(i) in used_sources:
                    file_name = node.metadata.get("file_name", "") if hasattr(node, "metadata") else getattr(node.node, "metadata", {}).get("file_name", "")
                    page = node.metadata.get("page_label", "") if hasattr(node, "metadata") else getattr(node.node, "metadata", {}).get("page_label", "")
                    source_key = f"{file_name}:::{page}"
                    if source_key not in seen_sources:
                        seen_sources.add(source_key)
                        filtered_sources.append({
                            "score": float(getattr(node, "score", 1.0) or 1.0),
                            "text": node.text if hasattr(node, "text") else getattr(node.node, "text", ""),
                            "metadata": node.metadata if hasattr(node, "metadata") else getattr(node.node, "metadata", {})
                        })
            
            # 6. Persist conversation to DB on thread pool (sync SQLAlchemy ops)
            sources_json = json.dumps(filtered_sources, ensure_ascii=False)
            session_title = session.title
            question_text = request.question

            def _persist_and_update_title():
                MessageRepository.create(db, session_id, "user", question_text)
                MessageRepository.create(db, session_id, "assistant", final_answer, sources_json)
                db.commit()

                # 7. Auto-generate title if still default
                if session_title == "Cuộc trò chuyện mới" or session_title == "New Chat" or not session_title.strip():
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

            yield f"data: {json.dumps({'sources': filtered_sources}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error processing chat message: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
