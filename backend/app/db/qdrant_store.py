from app.config import settings

import qdrant_client
from llama_index.vector_stores.qdrant import QdrantVectorStore


# Initialize the Qdrant vector store
def get_qdrant_client() -> qdrant_client.QdrantClient:
    return qdrant_client.QdrantClient(
        prefer_grpc=settings.QDRANT_PREFER_GRPC,
        url=settings.QDRANT_URL,
    )

# Initialize the Qdrant vector store
def init_qdrant_vector_store() -> QdrantVectorStore:
    client = get_qdrant_client()
    
    qdrant_vector_store = QdrantVectorStore(
        client=client,
        collection_name=settings.QDRANT_COLLECTION_NAME,
    )
    
    print("Initialized Qdrant Vector Store: ", settings.QDRANT_COLLECTION_NAME)
    return qdrant_vector_store