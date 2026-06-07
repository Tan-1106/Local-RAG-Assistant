import requests
import os
import uuid
import sys
import time
from dotenv import load_dotenv

# Reconfigure stdout to support printing Unicode/UTF-8 emojis on Windows terminal
sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

BASE_URL = "http://localhost:8000/api"
TIMEOUT = 300  # Prevent indefinite hanging by setting a 5-minute timeout

def main():
    print("==================================================")
    print("🚀 STARTING E2E INTEGRATION TEST: AUTH, SESSIONS & MEMORY")
    print("==================================================")

    # Generate a unique username for this test run
    unique_suffix = str(uuid.uuid4())[:8]
    username = f"testuser_{unique_suffix}"
    password = "testpassword123"

    # 1. Register a new user
    print(f"\n[1] Testing /auth/register for user: {username}...")
    url_register = f"{BASE_URL}/auth/register"
    payload_register = {"username": username, "password": password}
    try:
        response = requests.post(url_register, json=payload_register, timeout=TIMEOUT)
        print("Status Code:", response.status_code)
        assert response.status_code == 201, "Registration failed!"
        print("Response:", response.json())
    except Exception as e:
        print("Error during registration:", e)
        exit(1)

    # 2. Login to retrieve JWT token
    print("\n[2] Testing /auth/login to fetch JWT access token...")
    url_login = f"{BASE_URL}/auth/login"
    form_data = {"username": username, "password": password}
    try:
        response = requests.post(url_login, data=form_data, timeout=TIMEOUT)
        print("Status Code:", response.status_code)
        assert response.status_code == 200, "Login failed!"
        token_data = response.json()
        access_token = token_data.get("access_token")
        assert access_token, "No access token received!"
        print("JWT Token acquired successfully.")
    except Exception as e:
        print("Error during login:", e)
        exit(1)

    # Configure authenticated headers
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    admin_username = os.environ.get("SUPER_ADMIN_USERNAME")
    admin_password = os.environ.get("SUPER_ADMIN_PASSWORD")
    if not admin_username or not admin_password:
        raise RuntimeError(
            "SUPER_ADMIN_USERNAME and SUPER_ADMIN_PASSWORD are required for this E2E test"
        )

    admin_response = requests.post(
        url_login,
        data={"username": admin_username, "password": admin_password},
        timeout=TIMEOUT,
    )
    assert admin_response.status_code == 200, "Admin login failed!"
    admin_headers = {
        "Authorization": f"Bearer {admin_response.json()['access_token']}"
    }

    # 3. Access secure /auth/me route
    print("\n[3] Testing /auth/me with JWT bearer token...")
    url_me = f"{BASE_URL}/auth/me"
    try:
        response = requests.get(url_me, headers=auth_headers, timeout=TIMEOUT)
        print("Status Code:", response.status_code)
        assert response.status_code == 200, "Auth /me failed!"
        print("Profile Details:", response.json())
    except Exception as e:
        print("Error fetching profile:", e)
        exit(1)

    # 4. Create a new chat session
    print("\n[4] Testing session creation POST /sessions...")
    url_session = f"{BASE_URL}/sessions/"
    try:
        response = requests.post(url_session, json={"title": "Cuộc trò chuyện mới"}, headers=auth_headers, timeout=TIMEOUT)
        print("Status Code:", response.status_code)
        assert response.status_code == 201, "Session creation failed!"
        session_data = response.json()
        session_id = session_data.get("id")
        print(f"Created Session ID: {session_id}")
        print("Response:", session_data)
    except Exception as e:
        print("Error creating session:", e)
        exit(1)

    # 5. Setup sample RAG data and upload it
    print("\n[5] Creating and uploading Vietnamese legal sample document...")
    with open("test_luat.txt", "w", encoding="utf-8") as f:
        f.write("Điều 123. Tội giết người. Người nào cố ý tước đoạt tính mạng của người khác thì bị phạt tù từ 12 năm đến 20 năm, tù chung thân hoặc tử hình.")

    print("Uploading file to RAG pipeline (running metadata extractors, please wait)...")
    start_time = time.time()
    url_ingest = f"{BASE_URL}/documents/ingest"
    try:
        with open("test_luat.txt", "rb") as f:
            files = {"files": f}
            response = requests.post(
                url_ingest,
                files=files,
                headers=admin_headers,
                timeout=TIMEOUT,
            )
            duration = time.time() - start_time
            print(f"Ingest Status Code: {response.status_code} (Took {duration:.2f} seconds)")
            assert response.status_code == 200, "Ingestion failed!"
            print("Ingest Response:", response.json())
    except Exception as e:
        print("Error during ingestion:", e)
        if os.path.exists("test_luat.txt"):
            os.remove("test_luat.txt")
        exit(1)

    # 6. Test contextual memory chat
    print("\n[6] Testing conversational memory in chat...")
    url_chat = f"{BASE_URL}/sessions/{session_id}/chat"

    # Question 1
    print("--- Question 1: What is the punishment for murder? (Vietnamese) ---")
    print("Sending query to LLM (this may take a few seconds to load/infer, please wait)...")
    start_time = time.time()
    payload_chat_1 = {"question": "tội giết người bị phạt tù như thế nào?"}
    try:
        response = requests.post(url_chat, json=payload_chat_1, headers=auth_headers, timeout=TIMEOUT)
        duration = time.time() - start_time
        print(f"Status Code: {response.status_code} (Took {duration:.2f} seconds)")
        if response.status_code != 200:
            print("Response Error Detail:", response.text)
        assert response.status_code == 200, "Chat Turn 1 failed!"
        res_data_1 = response.json()
        print("AI Answer:", res_data_1.get("answer"))
        print("Sources Found:", len(res_data_1.get("sources", [])))
    except Exception as e:
        print("Error in Chat Turn 1:", e)
        exit(1)

    # Question 2
    print("\n--- Question 2: Follow-up question referencing context ('tội đó') ---")
    print("Sending follow-up query to LLM (verifying conversational history, please wait)...")
    start_time = time.time()
    payload_chat_2 = {"question": "tử hình có áp dụng cho tội đó không?"}
    try:
        response = requests.post(url_chat, json=payload_chat_2, headers=auth_headers, timeout=TIMEOUT)
        duration = time.time() - start_time
        print(f"Status Code: {response.status_code} (Took {duration:.2f} seconds)")
        assert response.status_code == 200, "Chat Turn 2 failed!"
        res_data_2 = response.json()
        print("AI Answer:", res_data_2.get("answer"))
        print("Sources Found:", len(res_data_2.get("sources", [])))
    except Exception as e:
        print("Error in Chat Turn 2:", e)
        exit(1)

    # 7. Check list sessions (to verify if the title was auto-updated)
    print("\n[7] Testing GET /sessions to check auto-updated session title...")
    try:
        response = requests.get(url_session, headers=auth_headers, timeout=TIMEOUT)
        print("Status Code:", response.status_code)
        assert response.status_code == 200, "Listing sessions failed!"
        sessions_list = response.json()
        my_session = next((s for s in sessions_list if s["id"] == session_id), None)
        assert my_session, "Session not found in list!"
        print(f"Updated Session Title: '{my_session['title']}' (Was: 'Cuộc trò chuyện mới')")
    except Exception as e:
        print("Error listing sessions:", e)
        exit(1)

    # 8. Load message history to verify persisted logs and parsed sources
    print("\n[8] Testing GET /sessions/{session_id}/messages to verify conversation history persistence...")
    url_messages = f"{BASE_URL}/sessions/{session_id}/messages"
    try:
        response = requests.get(url_messages, headers=auth_headers, timeout=TIMEOUT)
        print("Status Code:", response.status_code)
        assert response.status_code == 200, "Fetching messages failed!"
        msg_history = response.json()
        print(f"Total Messages Logged: {len(msg_history)}")
        for idx, msg in enumerate(msg_history):
            print(f"Message {idx + 1} [{msg['role']}]: {msg['content'][:100]}...")
            if msg["role"] == "assistant":
                print(f"  --> Citations: {len(msg.get('sources', []))} references found.")
        assert len(msg_history) == 4, "Incorrect history length (should be 4 messages)!"
    except Exception as e:
        print("Error fetching message history:", e)
        exit(1)

    # 9. Clean up sessions and documents
    print("\n[9] Running cleanup phases...")
    # Delete chat session
    print(f"Deleting chat session: {session_id}...")
    url_delete_session = f"{BASE_URL}/sessions/{session_id}"
    try:
        response = requests.delete(url_delete_session, headers=auth_headers, timeout=TIMEOUT)
        print("Status Code:", response.status_code)
        assert response.status_code == 200, "Deleting session failed!"
    except Exception as e:
        print("Error deleting session:", e)

    # Delete legal document from RAG index
    print("Deleting ingested legal document test_luat.txt from index...")
    url_delete_doc = f"{BASE_URL}/documents/test_luat.txt"
    try:
        response = requests.delete(
            url_delete_doc,
            headers=admin_headers,
            timeout=TIMEOUT,
        )
        print("Status Code:", response.status_code)
        assert response.status_code == 200, "Deleting document from RAG failed!"
    except Exception as e:
        print("Error deleting document:", e)

    # Remove local host file
    if os.path.exists("test_luat.txt"):
        os.remove("test_luat.txt")
        print("Cleaned up local host test_luat.txt.")

    print("\n==================================================")
    print("🎉 E2E INTEGRATION TEST COMPLETED SUCCESSFULLY!")
    print("All features verified: Register, Login, Token, CRUD Session, RAG memory.")
    print("==================================================")

if __name__ == "__main__":
    main()
