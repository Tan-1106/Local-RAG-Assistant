import uuid
import json
from typing                 import Optional, Dict, Any
from app.logger             import get_logger
from app.db.redis_store     import get_redis_client

logger = get_logger(__name__)

class TaskTrackerService:
    def __init__(self):
        self._redis = get_redis_client()
        self.default_ttl = 86400  # 24 hours

    def create_task(self, task_type: str, meta: Optional[Dict[str, Any]] = None) -> str:
        """
        Creates a new task in Redis and returns the task ID.
        """
        task_id = f"task:{task_type}:{uuid.uuid4().hex}"
        
        task_data = {
            "status": "processing",
            "error": "",
        }
        if meta:
            # Store meta as a JSON string to avoid nested hash issues in Redis
            task_data["meta"] = json.dumps(meta)
            
        try:
            self._redis.hset(task_id, mapping=task_data)
            self._redis.expire(task_id, self.default_ttl)
            logger.info(f"Created task {task_id} with status 'processing'")
        except Exception as e:
            logger.error(f"Failed to create task {task_id} in Redis: {e}")
            
        return task_id

    def update_task_status(self, task_id: str, status: str, error: Optional[str] = None):
        """
        Updates the status of an existing task.
        """
        if not task_id:
            return
            
        update_data = {"status": status}
        if error is not None:
            update_data["error"] = error
            
        try:
            self._redis.hset(task_id, mapping=update_data)
            logger.info(f"Updated task {task_id} status to '{status}'")
        except Exception as e:
            logger.error(f"Failed to update task {task_id} in Redis: {e}")

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a task's status and details from Redis.
        """
        try:
            data = self._redis.hgetall(task_id)
            if not data:
                return None
                
            # Parse meta back to dict if it exists
            if "meta" in data and data["meta"]:
                try:
                    data["meta"] = json.loads(data["meta"])
                except json.JSONDecodeError:
                    pass
                    
            return data
        except Exception as e:
            logger.error(f"Failed to retrieve task {task_id} from Redis: {e}")
            # Fallback for when Redis is down but client asks
            return {"status": "error", "error": f"Redis connection error: {str(e)}"}

# Dependency Injection helper
def get_task_service() -> TaskTrackerService:
    return TaskTrackerService()
