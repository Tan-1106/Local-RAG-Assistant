import os
import shutil
import tempfile
from typing                     import List
from fastapi                    import APIRouter, UploadFile, File, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses          import FileResponse
from app.config                 import settings
from app.models.all_models      import User
from app.services.auth_service  import get_current_user, get_current_admin_user
from app.services.rag_pipeline  import (
    delete_document,
    ingest_documents,
    background_ingest_uploaded_documents,
)


router = APIRouter(prefix="/documents", tags=["Documents & RAG"])


@router.post("/ingest", status_code=202)
def ingest_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Upload legal documents, stage them, and queue the ingestion pipeline in the background.

    Args:
        files (List[UploadFile]): A list of uploaded files to process.
        chat_engine (ContextChatEngine): The global AI chat engine dependency.

    Returns:
        dict: A status dictionary containing the number of queued files.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
        
    try:
        # Ensure data directory exists
        os.makedirs(settings.DATA_DIR, exist_ok=True)
        
        saved_files = []
        staging_dir = tempfile.mkdtemp(dir=settings.DATA_DIR)
        for file in files:
            safe_filename = os.path.basename(file.filename or "")
            if not safe_filename:
                raise HTTPException(status_code=400, detail="Invalid filename")

            staged_path = os.path.join(staging_dir, safe_filename)
            with open(staged_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_files.append(safe_filename)

        background_tasks.add_task(
            background_ingest_uploaded_documents,
            staging_dir=staging_dir,
            filenames=saved_files,
            target_dir=settings.DATA_DIR,
        )
        
        # Clear cached retriever and index
        request.app.state.retriever = None
        request.app.state.index = None
        
        return {
            "status": "processing",
            "message": f"Queued {len(saved_files)} files for background ingestion.",
            "files": saved_files
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Manual synchronization and document deletion
@router.post("/sync", status_code=202)
def sync_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Queue synchronization of the vector database with all existing documents in the DATA_DIR.
    This is useful for manually placed files.

    Returns:
        dict: A status message detailing the sync result.
    """
    try:
        # Ensure data directory exists
        os.makedirs(settings.DATA_DIR, exist_ok=True)
        
        # Get list of existing files
        existing_files = os.listdir(settings.DATA_DIR)
        if not existing_files:
            return {
                "status": "info",
                "message": "No files found in the data directory to sync."
            }
            
        # Run the RAG ingestion pipeline (sync all) in background
        background_tasks.add_task(ingest_documents, data_path=settings.DATA_DIR)
        
        # Clear cached retriever and index
        request.app.state.retriever = None
        request.app.state.index = None
        
        return {
            "status": "processing",
            "message": f"Queued {len(existing_files)} existing files for background synchronization."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Document deletion
@router.delete("/{filename}")
def delete_document_endpoint(
    filename: str,
    request: Request,
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Delete a document and its vectors from the system.

    Args:
        filename (str): The name of the file to delete.
        chat_engine (ContextChatEngine): The global AI chat engine dependency.

    Returns:
        dict: A status dictionary detailing the deletion results.
    """
    try:
        # Prevent Path Traversal
        filename = os.path.basename(filename)
        result = delete_document(filename)
        if not result["deleted_from_disk"] and result["nodes_deleted_from_docstore"] == 0:
            raise HTTPException(status_code=404, detail="Document not found")
            
        # Clear cached retriever and index
        request.app.state.retriever = None
        request.app.state.index = None
            
        return {
            "status": "success",
            "message": f"Successfully deleted '{filename}'",
            "details": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/file/{filename}", response_class=FileResponse)
def get_document_file(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve and stream an ingested document file, verified by authentication.

    Args:
        filename (str): The name of the file to retrieve.
        current_user (User): The authenticated user dependency.

    Returns:
        FileResponse: The streamed document file.
    """
    filename = os.path.basename(filename)
    file_path = os.path.join(settings.DATA_DIR, filename)

    data_dir = os.path.abspath(settings.DATA_DIR)
    if os.path.commonpath([data_dir, os.path.abspath(file_path)]) != data_dir:
        raise HTTPException(status_code=400, detail="Invalid file path")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine the correct media type, defaulting to octet-stream
    media_type = "application/pdf" if filename.lower().endswith(".pdf") else "application/octet-stream"
    
    return FileResponse(file_path, media_type=media_type, filename=filename)
