import qdrant_client
from app.config                         import settings
from llama_index.vector_stores.qdrant   import QdrantVectorStore
from app.logger                         import get_logger

logger = get_logger(__name__)

# Initialize the Qdrant vector store
def get_qdrant_client() -> qdrant_client.QdrantClient:
    """
    Create and return a Qdrant client instance based on configuration settings.

    Returns:
        qdrant_client.QdrantClient: The initialized Qdrant client.
    """
    return qdrant_client.QdrantClient(
        prefer_grpc=settings.QDRANT_PREFER_GRPC,
        url=settings.QDRANT_URL,
    )

# Initialize the Qdrant vector store
def init_qdrant_vector_store() -> QdrantVectorStore:
    """
    Initialize and return a Qdrant vector store instance.

    Returns:
        QdrantVectorStore: The initialized vector store ready for indexing.
    """
    client = get_qdrant_client()
    
    qdrant_vector_store = QdrantVectorStore(
        client=client,
        collection_name=settings.QDRANT_COLLECTION_NAME,
    )
    
    logger.info(f"Initialized Qdrant Vector Store: {settings.QDRANT_COLLECTION_NAME}")
    return qdrant_vector_store