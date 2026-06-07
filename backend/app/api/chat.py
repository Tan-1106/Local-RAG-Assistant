from llama_index.core.chat_engine   import ContextChatEngine
from llama_index.core.retrievers    import AutoMergingRetriever
import json
from fastapi                        import APIRouter, Depends
from fastapi.responses              import StreamingResponse
from app.services.chat_engine       import get_retriever
from app.schemas.chat               import ChatRequest
from app.models.all_models          import User
from app.services.auth_service      import get_current_user


router = APIRouter(prefix="/chat", tags=["Generic Chat (No Session)"])

@router.post("/")
def chat_endpoint(
    request: ChatRequest,
    retriever: AutoMergingRetriever = Depends(get_retriever),
    current_user: User = Depends(get_current_user)
):
    """
    Process a legal question using the RAG pipeline and stream the answer with sources via SSE.
    This endpoint does not save conversation history.
    """
    def generate_stream():
        try:
            chat_engine = ContextChatEngine.from_defaults(retriever=retriever, verbose=True)
            response = chat_engine.stream_chat(request.question)
            
            for token in response.response_gen:
                yield f"data: {json.dumps({'chunk': token}, ensure_ascii=False)}\n\n"
                
            # Extract sources
            sources = []
            if hasattr(response, "source_nodes") and response.source_nodes:
                for node in response.source_nodes:
                    sources.append({
                        "score": float(node.score) if node.score else 0.0,
                        "text": node.text,
                        "metadata": node.metadata
                    })
            
            yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            
    return StreamingResponse(generate_stream(), media_type="text/event-stream")
