import os
import sys
import pytest

# Reconfigure stdout to support printing Unicode/UTF-8 emojis on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

pytest.importorskip("llama_index")

from fastapi.testclient import TestClient

# Ensure backend directory is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.main import app
from app.config import settings
from app.services.auth_service import get_current_user
from app.models.all_models import User

def test_document_file_endpoint():
    print("🧪 [Test] Starting document file serving endpoint tests...")

    # 1. Test without authentication (No headers)
    client = TestClient(app)
    print("  -> Testing unauthorized access...")
    response = client.get("/api/documents/file/sample.pdf")
    print(f"     Status Code: {response.status_code}")
    assert response.status_code == 401, "Expected 401 Unauthorized for unauthenticated request"
    
    # 2. Test with authentication (Override get_current_user dependency)
    print("  -> Overriding authentication dependency with a mock user...")
    mock_user = User(id=999, username="mocktestuser")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    
    try:
        # 3. Test with non-existent file
        print("  -> Testing authorized access for a non-existent file...")
        response = client.get("/api/documents/file/non_existent_file_xyz.pdf")
        print(f"     Status Code: {response.status_code}")
        assert response.status_code == 404, "Expected 404 Not Found for non-existent file"
        
        # 4. Test with an existing file
        print("  -> Creating a temporary dummy document...")
        os.makedirs(settings.DATA_DIR, exist_ok=True)
        test_filename = "test_document_endpoint_serving.pdf"
        test_file_path = os.path.join(settings.DATA_DIR, test_filename)
        dummy_content = b"PDF dummy content streaming verification"
        
        with open(test_file_path, "wb") as f:
            f.write(dummy_content)
            
        try:
            print("  -> Testing authorized access to stream the existing file...")
            response = client.get(f"/api/documents/file/{test_filename}")
            print(f"     Status Code: {response.status_code}")
            print(f"     Content-Type: {response.headers.get('content-type')}")
            
            assert response.status_code == 200, "Expected 200 OK"
            assert response.headers.get("content-type") == "application/pdf", "Expected application/pdf content type"
            assert response.content == dummy_content, "Streamed content mismatch"
            print("     Content matched successfully!")
            
        finally:
            if os.path.exists(test_file_path):
                os.remove(test_file_path)
                print("  -> Cleaned up temporary document.")
                
    finally:
        # Clear dependency overrides
        app.dependency_overrides.clear()
        print("  -> Restored dependencies.")

    print("🎉 [Test] All tests passed successfully!")

if __name__ == "__main__":
    test_document_file_endpoint()
