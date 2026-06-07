import os
from app.config                         import settings
from app.logger                         import get_logger
from app.db.redis_store                 import get_redis_client
from fastapi                            import Request
from llama_index.core.retrievers        import AutoMergingRetriever
from llama_index.core                   import StorageContext
from llama_index.core.storage.docstore  import SimpleDocumentStore

logger = get_logger(__name__)

def get_retriever(request: Request) -> AutoMergingRetriever:
    """
    FastAPI Dependency to lazy-load and retrieve the pre-initialized retriever.
    Re-builds if cleared from cache or AI components failed to initialize.
    """
    if not getattr(request.app.state, "ai_initialized", False):
        logger.info("🚀 [AI Logic] Retrying AI system initialization...")
        from app.services.ai_logic import initialize_ai
        try:
            initialize_ai()
            request.app.state.ai_initialized = True
        except Exception as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail="AI Initialization failed, please check models and vector store.")

    cached_version = getattr(request.app.state, "retriever_version", None)
    try:
        index_version = int(get_redis_client().get("rag:index-version") or 0)
    except Exception as error:
        logger.warning("Could not read RAG index version: %s", error)
        index_version = cached_version

    if (
        not hasattr(request.app.state, "retriever")
        or request.app.state.retriever is None
        or cached_version != index_version
    ):
        logger.info("🚀 [AI Logic] Building Global Retriever...")
        from app.services.rag_pipeline import get_index
        index = get_index()
        
        # Dynamically check format if Qdrant was empty before
        vector_store = index.storage_context.vector_store
        if vector_store and not getattr(vector_store, "_collection_initialized", False):
            client = getattr(vector_store, "_client", None)
            collection_name = getattr(vector_store, "collection_name", None)
            if client and collection_name:
                try:
                    if client.collection_exists(collection_name):
                        vector_store._collection_initialized = True
                        if hasattr(vector_store, "_detect_vector_format"):
                            vector_store._detect_vector_format(collection_name)
                            logger.info("🚀 [AI Logic] Dynamically detected Qdrant vector format on query.")
                except Exception as e:
                    logger.warning(f"⚠️ [AI Logic] Failed to dynamically detect vector format: {e}")

        base_retriever = index.as_retriever(similarity_top_k=12)
        docstore_path = settings.DOCSTORE_PATH
        if os.path.exists(docstore_path):
            docstore = SimpleDocumentStore.from_persist_path(docstore_path)
        else:
            docstore = SimpleDocumentStore()

        storage_context = StorageContext.from_defaults(
            vector_store=vector_store,
            docstore=docstore
        )

        retriever = AutoMergingRetriever(
            base_retriever,
            storage_context=storage_context,
            verbose=True
        )
        request.app.state.retriever = retriever
        request.app.state.retriever_version = index_version
    
    return request.app.state.retriever
