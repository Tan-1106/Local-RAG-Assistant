import uuid
from typing import Any, Dict, Optional

from rq import Queue, Retry
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.config import settings
from app.db.redis_store import get_rq_redis_client
from app.logger import get_logger

logger = get_logger(__name__)


class TaskTrackerService:
    def __init__(self, queue: Queue | None = None):
        self._redis = get_rq_redis_client()
        self._queue = queue or Queue(settings.RQ_QUEUE_NAME, connection=self._redis)

    def _enqueue(
        self,
        function,
        *,
        task_type: str,
        kwargs: Dict[str, Any],
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        task_id = f"task_{task_type}_{uuid.uuid4().hex}"
        self._queue.enqueue_call(
            function,
            kwargs=kwargs,
            job_id=task_id,
            meta={"type": task_type, **(meta or {})},
            retry=Retry(max=3, interval=[30, 120, 300]),
            timeout=settings.RQ_JOB_TIMEOUT_SECONDS,
            result_ttl=settings.RQ_RESULT_TTL_SECONDS,
            failure_ttl=settings.RQ_FAILURE_TTL_SECONDS,
        )
        logger.info("Queued RQ job %s on %s", task_id, settings.RQ_QUEUE_NAME)
        return task_id

    def enqueue_upload(
        self,
        staging_dir: str,
        filenames: list[str],
        target_dir: str,
    ) -> str:
        return self._enqueue(
            "app.services.rag_pipeline.background_ingest_uploaded_documents",
            task_type="ingest",
            kwargs={
                "staging_dir": staging_dir,
                "filenames": filenames,
                "target_dir": target_dir,
            },
            meta={"files": filenames},
        )

    def enqueue_sync(self, data_path: str, file_count: int) -> str:
        return self._enqueue(
            "app.services.rag_pipeline.run_sync_ingestion_job",
            task_type="sync",
            kwargs={"data_path": data_path},
            meta={"count": file_count},
        )

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        try:
            job = Job.fetch(task_id, connection=self._redis)
        except NoSuchJobError:
            return None

        raw_status = job.get_status(refresh=True)
        status_value = getattr(raw_status, "value", str(raw_status))
        status_map = {
            "queued": "queued",
            "deferred": "queued",
            "scheduled": "queued",
            "started": "processing",
            "finished": "completed",
            "failed": "failed",
            "stopped": "failed",
            "canceled": "failed",
        }
        status = status_map.get(status_value, status_value)
        error = ""
        if status == "failed" and job.exc_info:
            error = job.exc_info.strip().splitlines()[-1]

        return {
            "task_id": job.id,
            "type": job.meta.get("type", "unknown"),
            "status": status,
            "meta": {
                key: value
                for key, value in job.meta.items()
                if key != "type"
            },
            "error": error,
        }


def get_task_service() -> TaskTrackerService:
    return TaskTrackerService()
