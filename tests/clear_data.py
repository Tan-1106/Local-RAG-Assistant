import os
import sys
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

def clear_all():
    print("🧹 [Cleanup] Starting full data cleanup...")
    
    # 1. Clear Qdrant collection
    try:
        print("  -> Deleting Qdrant collection 'legal_documents'...")
        resp = requests.delete("http://localhost:6333/collections/legal_documents")
        print("     Response:", resp.status_code, resp.json())
    except Exception as e:
        print("     Failed to delete Qdrant collection:", e)
        
    # 2. Resolve Paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "backend", "data")
    storage_dir = os.path.join(base_dir, "backend", "storage")
    
    # 3. Delete db.sqlite3
    db_path = os.path.join(data_dir, "db.sqlite3")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("  -> Deleted SQLite database file 'db.sqlite3'.")
        except Exception as e:
            print(f"     Failed to delete db.sqlite3: {e}")
            
    # 4. Delete docstore.json
    docstore_path = os.path.join(storage_dir, "docstore.json")
    if os.path.exists(docstore_path):
        try:
            os.remove(docstore_path)
            print("  -> Deleted docstore file 'docstore.json'.")
        except Exception as e:
            print(f"     Failed to delete docstore.json: {e}")
            
    # 5. Delete other test files in data_dir
    if os.path.exists(data_dir):
        for item in os.listdir(data_dir):
            item_path = os.path.join(data_dir, item)
            if os.path.isfile(item_path) and item != "db.sqlite3":
                try:
                    os.remove(item_path)
                    print(f"  -> Deleted test document: {item}")
                except Exception as e:
                    print(f"     Failed to delete {item}: {e}")
                    
    print("✨ [Cleanup] Finished full data cleanup successfully!")

if __name__ == "__main__":
    clear_all()
