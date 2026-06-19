import os
import threading
import uuid
from pathlib import Path
from qdrant_client.http                 import models as qdrant_models
from llama_index.core.storage.docstore  import SimpleDocumentStore
from llama_index.core.node_parser       import HierarchicalNodeParser, get_leaf_nodes
from llama_index.core                   import SimpleDirectoryReader, StorageContext, VectorStoreIndex
from app.config                         import settings
from app.db.qdrant_store                import init_qdrant_vector_store
from app.logger                         import get_logger
from app.services.task_service          import TaskTrackerService

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


def ingest_documents(data_path: str = None, specific_files: list[str] = None, task_id: str = None):
    try:
        with _index_lock:
            result = _ingest_documents(data_path, specific_files)
        if task_id:
            TaskTrackerService().update_task_status(task_id, "completed")
        return result
    except Exception as e:
        logger.error(f"Sync ingestion failed: {e}")
        if task_id:
            TaskTrackerService().update_task_status(task_id, "failed", error=str(e))
        raise


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

def background_ingest_uploaded_documents(staging_dir: str, filenames: list[str], target_dir: str, task_id: str = None):
    import shutil
    try:
        ingest_uploaded_documents(staging_dir, filenames, target_dir)
        logger.info(f"Background ingestion of {len(filenames)} files completed successfully.")
        if task_id:
            TaskTrackerService().update_task_status(task_id, "completed")
        shutil.rmtree(staging_dir, ignore_errors=True)
    except Exception as e:
        logger.error(f"Background ingestion failed: {e}")
        if task_id:
            TaskTrackerService().update_task_status(task_id, "failed", error=str(e))
        import rq
        job = rq.get_current_job()
        if not job or getattr(job, 'retries_left', 0) == 0:
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise

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
            logger.error("No specific files found to ingest.")
            raise FileNotFoundError("No specific files found to ingest.")
    else:
        if not os.path.exists(path) or len(os.listdir(path)) == 0:
            logger.info(f"No documents found in {path}. Please add documents to ingest.")
            return

    from app.services.smart_pdf_reader import SmartPDFReader

    file_extractor = {".pdf": SmartPDFReader()}
    if input_files:
        documents = SimpleDirectoryReader(
            input_files=input_files,
            file_extractor=file_extractor
        ).load_data()
    else:
        documents = SimpleDirectoryReader(
            path,
            required_exts=[".pdf", ".txt", ".docx", ".doc"],
            file_extractor=file_extractor
        ).load_data()

    if not documents:
        logger.warning("No valid documents found to ingest.")
        return

    for document in documents:
        file_name = document.metadata.get("file_name", "")
        source = document.metadata.get("source")
        if source is not None:
            document.metadata["page_label"] = str(source)
        if file_name:
            document.metadata["document_title"] = Path(file_name).stem

        document.excluded_embed_metadata_keys = list({
            *document.excluded_embed_metadata_keys,
            "document_title",
            "file_path",
            "ingestion_id",
            "page_label",
            "source",
            "total_pages",
        })
        document.excluded_llm_metadata_keys = list({
            *document.excluded_llm_metadata_keys,
            "file_path",
            "ingestion_id",
            "source",
            "total_pages",
        })

    node_parser = HierarchicalNodeParser.from_defaults(
        chunk_sizes=[1024, 512, 256],
        chunk_overlap=48,
    )

    logger.info("Running ingestion pipeline...")
    nodes = node_parser.get_nodes_from_documents(documents)
    ingestion_id = str(uuid.uuid4())
    for node in nodes:
        node.metadata["ingestion_id"] = ingestion_id
        if "ingestion_id" not in node.excluded_embed_metadata_keys:
            node.excluded_embed_metadata_keys.append("ingestion_id")
        if "ingestion_id" not in node.excluded_llm_metadata_keys:
            node.excluded_llm_metadata_keys.append("ingestion_id")

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

    try:
        from app.db.redis_store import get_redis_client

        get_redis_client().incr("rag:index-version")
    except Exception as error:
        logger.warning("Could not invalidate the cached RAG retriever: %s", error)

    return index


def delete_document(filename: str, keep_file: bool = False):
    with _index_lock:
        return _delete_document(filename, keep_file)


def delete_all_documents():
    """
    Deletes all documents from the local disk, Qdrant vector store, and local Docstore.
    """
    with _index_lock:
        data_dir = os.path.abspath(settings.DATA_DIR)
        if not os.path.exists(data_dir):
            return {"deleted_files": 0, "nodes_deleted_from_docstore": 0}

        deleted_files_count = 0
        total_nodes_deleted = 0

        for filename in os.listdir(data_dir):
            file_path = os.path.join(data_dir, filename)
            if os.path.isfile(file_path):
                try:
                    result = _delete_document(filename)
                    if result["deleted_from_disk"]:
                        deleted_files_count += 1
                    total_nodes_deleted += result["nodes_deleted_from_docstore"]
                except Exception as e:
                    logger.error(f"Failed to delete {filename}: {e}")

        return {
            "deleted_files": deleted_files_count,
            "nodes_deleted_from_docstore": total_nodes_deleted
        }


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
