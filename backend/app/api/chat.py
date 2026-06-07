from llama_index.core.chat_engine   import ContextChatEngine
from llama_index.core.retrievers    import AutoMergingRetriever
from fastapi                        import APIRouter, Depends, HTTPException
from app.services.chat_engine       import get_retriever
from app.schemas.chat               import ChatRequest, ChatResponse, SourceNode
from app.models.all_models          import User
from app.services.auth_service      import get_current_user


router = APIRouter(prefix="/chat", tags=["Generic Chat (No Session)"])

@router.post("/", response_model=ChatResponse)
def chat_endpoint(
    request: ChatRequest,
    retriever: AutoMergingRetriever = Depends(get_retriever),
    current_user: User = Depends(get_current_user)
):
    """
    Process a legal question using the RAG pipeline and return the answer with sources.
    This endpoint does not save conversation history.
    """
    try:
        chat_engine = ContextChatEngine.from_defaults(retriever=retriever, verbose=True)
        response = chat_engine.chat(request.question)
        
        # Extract sources
        sources = []
        if hasattr(response, "source_nodes") and response.source_nodes:
            for node in response.source_nodes:
                sources.append({
                    "score": float(node.score) if node.score else 0.0,
                    "text": node.text,
                    "metadata": node.metadata
                })
        
        # Map the dictionary output to Pydantic models
        sources_response = [
            SourceNode(
                score=source["score"],
                text=source["text"],
                metadata=source["metadata"]
            )
            for source in sources
        ]
        
        return ChatResponse(
            answer=response.response.strip(),
            sources=sources_response
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
