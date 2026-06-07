import os
import threading
import uuid
from qdrant_client.http                 import models as qdrant_models
from llama_index.core.storage.docstore  import SimpleDocumentStore
from llama_index.core.node_parser       import HierarchicalNodeParser, get_leaf_nodes
from llama_index.core                   import SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.core.extractors        import TitleExtractor, KeywordExtractor
from llama_index.core.ingestion         import IngestionPipeline
from app.config                         import settings
from app.db.qdrant_store                import init_qdrant_vector_store
from app.logger                         import get_logger

logger = get_logger(__name__)

_index_lock = threading.RLock()


def get_index():
    """
    Build a VectorStoreIndex backed by the configured Qdrant collection.
    """
    docstore_path = settings.DOCSTORE_PATH
    if os.path.exists(docstore_path):
        docstore = SimpleDocumentStore.from_persist_path(docstore_path)
    else:
        docstore = SimpleDocumentStore()

    vector_store = init_qdrant_vector_store()
    storage_context = StorageContext.from_defaults(
        docstore=docstore,
        vector_store=vector_store,
    )
    # Return index built from vector store
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        storage_context=storage_context
    )
    return index


def _delete_indexed_document(filename: str, preserve_ingestion_id: str | None = None) -> int:
    """
    Delete indexed nodes for a document while optionally retaining one ingestion version.
    """
    filename = os.path.basename(filename)
    vector_store = init_qdrant_vector_store()
    client = vector_store.client

    must_not = []
    if preserve_ingestion_id:
        must_not.append(
            qdrant_models.FieldCondition(
                key="ingestion_id",
                match=qdrant_models.MatchValue(value=preserve_ingestion_id),
            )
        )

    client.delete(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points_selector=qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="file_name",
                    match=qdrant_models.MatchValue(value=filename),
                )
            ],
            must_not=must_not,
        ),
    )

    docstore_path = settings.DOCSTORE_PATH
    if not os.path.exists(docstore_path):
        return 0

    docstore = SimpleDocumentStore.from_persist_path(docstore_path)
    docs_to_delete = [
        doc_id
        for doc_id, doc in docstore.docs.items()
        if doc.metadata.get("file_name") == filename
        and (
            not preserve_ingestion_id
            or doc.metadata.get("ingestion_id") != preserve_ingestion_id
        )
    ]
    for doc_id in docs_to_delete:
        docstore.delete_document(doc_id)

    if docs_to_delete:
        docstore.persist(docstore_path)
    return len(docs_to_delete)


def ingest_documents(data_path: str = None, specific_files: list[str] = None):
    with _index_lock:
        return _ingest_documents(data_path, specific_files)


def ingest_uploaded_documents(
    staging_dir: str,
    filenames: list[str],
    target_dir: str,
):
    """Index staged uploads and publish source files as one serialized operation."""
    with _index_lock:
        index = _ingest_documents(staging_dir, filenames)
        for filename in filenames:
            os.replace(
                os.path.join(staging_dir, filename),
                os.path.join(target_dir, filename),
            )
        return index

def background_ingest_uploaded_documents(staging_dir: str, filenames: list[str], target_dir: str):
    import shutil
    try:
        ingest_uploaded_documents(staging_dir, filenames, target_dir)
        logger.info(f"Background ingestion of {len(filenames)} files completed successfully.")
    except Exception as e:
        logger.error(f"Background ingestion failed: {e}")
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

def _ingest_documents(data_path: str = None, specific_files: list[str] = None):
    """
    Ingests documents from a specified directory or a list of specific files.
    Writes the new version before removing old indexed versions.
    """
    path = data_path or settings.DATA_DIR

    input_files = None
    if specific_files:
        input_files = [os.path.join(path, f) for f in specific_files if os.path.exists(os.path.join(path, f))]
        if not input_files:
            logger.info("No specific files found to ingest.")
            return
    else:
        if not os.path.exists(path) or len(os.listdir(path)) == 0:
            logger.info(f"No documents found in {path}. Please add documents to ingest.")
            return

    if input_files:
        documents = SimpleDirectoryReader(input_files=input_files).load_data()
    else:
        documents = SimpleDirectoryReader(
            path,
            required_exts=[".pdf", ".txt", ".docx", ".doc"]
        ).load_data()

    if not documents:
        logger.warning("No valid documents found to ingest.")
        return

    node_parser = HierarchicalNodeParser.from_defaults(
        chunk_sizes=[1024, 512, 128]
    )
    extractors = [
        TitleExtractor(nodes=5),
        KeywordExtractor(keywords=5)
    ]
    
    # Run the Ingestion Pipeline
    pipeline = IngestionPipeline(
        transformations=[node_parser] + extractors
    )

    logger.info("Running Ingestion Pipeline (This may take a while due to metadata extraction)...")
    nodes = pipeline.run(documents=documents)
    ingestion_id = str(uuid.uuid4())
    for node in nodes:
        node.metadata["ingestion_id"] = ingestion_id

    leaf_nodes = get_leaf_nodes(nodes)
    docstore_path = settings.DOCSTORE_PATH
    if os.path.exists(docstore_path):
        docstore = SimpleDocumentStore.from_persist_path(docstore_path)
    else:
        docstore = SimpleDocumentStore()

    docstore.add_documents(nodes)
    vector_store = init_qdrant_vector_store()
    storage_context = StorageContext.from_defaults(
        docstore=docstore,
        vector_store=vector_store,
    )

    # Insert the replacement version first. If this fails, the previous index remains intact.
    index = VectorStoreIndex(
        leaf_nodes,
        storage_context=storage_context
    )

    docstore_dir = os.path.dirname(docstore_path)
    if docstore_dir:
        os.makedirs(docstore_dir, exist_ok=True)
    docstore.persist(docstore_path)

    filenames = {
        os.path.basename(doc.metadata["file_name"])
        for doc in documents
        if doc.metadata.get("file_name")
    }
    for filename in filenames:
        _delete_indexed_document(filename, preserve_ingestion_id=ingestion_id)

    return index


def delete_document(filename: str, keep_file: bool = False):
    with _index_lock:
        return _delete_document(filename, keep_file)


def _delete_document(filename: str, keep_file: bool = False):
    """
    Deletes a document from the local disk, Qdrant vector store, and local Docstore.
    If keep_file is True, only vector store and docstore entries are deleted.
    """
    filename = os.path.basename(filename)
    deleted_from_disk = False
    file_path = os.path.join(settings.DATA_DIR, filename)

    data_dir = os.path.abspath(settings.DATA_DIR)
    if os.path.commonpath([data_dir, os.path.abspath(file_path)]) != data_dir:
        raise ValueError("Invalid file path")

    if not keep_file and os.path.exists(file_path):
        os.remove(file_path)
        deleted_from_disk = True

    try:
        nodes_deleted = _delete_indexed_document(filename)
    except Exception as e:
        raise RuntimeError(f"Failed to delete from Qdrant: {e}")

    return {
        "deleted_from_disk": deleted_from_disk,
        "nodes_deleted_from_docstore": nodes_deleted
    }
