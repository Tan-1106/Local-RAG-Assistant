import os
from app.config import settings

from app.db.qdrant_store import init_qdrant_vector_store
from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.storage.docstore import SimpleDocumentStore


# Function to get the chat query engine
def get_chat_query_engine():
    # Initialize connection to Qdrant vector store
    vector_store = init_qdrant_vector_store()
    
    # Build index from vector_store
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store
    )
    
    # Initialize base retriever to get the top 12 closest leaf nodes
    base_retriever = index.as_retriever(similarity_top_k=12)
    
    # Load document store from static file saved during ingest step to access Parent Nodes
    docstore_path = settings.DOCSTORE_PATH
    if os.path.exists(docstore_path):
        docstore = SimpleDocumentStore.from_persist_path(docstore_path)
    else:
        docstore = SimpleDocumentStore()
        
    # Pass both vector_store and docstore into Storage Context
    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
        docstore=docstore
    )
    
    # Use AutoMergingRetriever to merge leaf nodes into parent nodes
    # (Relies on parent_id in leaf nodes to look up parent nodes in docstore)
    retriever = AutoMergingRetriever(
        base_retriever, 
        storage_context=storage_context, 
        verbose=True
    )
    
    # Create query engine from retriever
    query_engine = RetrieverQueryEngine.from_args(
        retriever=retriever,
    )
    
    return query_engine


# Function to answer legal questions using the chat query engine
def answer_legal_question(question: str) -> dict:
    # Get the configured chat query engine
    query_engine = get_chat_query_engine()
    
    # Query the engine with the user's question
    response = query_engine.query(question)
    
    # Extract the source nodes used to generate the answer
    sources = []
    for node in response.source_nodes:
        sources.append({
            "score": float(node.score) if node.score else 0.0,
            "text": node.text,
            "metadata": node.metadata
        })
        
    # Return the generated answer along with the reference sources
    return {
        "answer": response.response.strip(),
        "sources": sources
    }