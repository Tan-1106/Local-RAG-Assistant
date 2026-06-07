import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.services import task_service
from app.services.task_service import TaskTrackerService


class FakeQueue:
    def __init__(self):
        self.calls = []

    def enqueue_call(self, function, **options):
        self.calls.append((function, options))


class FakeJob:
    id = "task:ingest:123"
    meta = {"type": "ingest", "files": ["law.pdf"]}
    exc_info = None

    def get_status(self, refresh=False):
        assert refresh is True
        return "started"


def test_upload_is_enqueued_with_retry_and_timeout():
    queue = FakeQueue()
    service = TaskTrackerService(queue=queue)

    task_id = service.enqueue_upload("/staging", ["law.pdf"], "/data")

    assert task_id.startswith("task:ingest:")
    _, options = queue.calls[0]
    assert options["job_id"] == task_id
    assert options["meta"]["files"] == ["law.pdf"]
    assert options["retry"].max == 3
    assert options["job_timeout"] > 0


def test_rq_started_status_maps_to_processing(monkeypatch):
    service = TaskTrackerService(queue=FakeQueue())
    monkeypatch.setattr(
        task_service.Job,
        "fetch",
        classmethod(lambda _cls, _task_id, connection: FakeJob()),
    )

    task = service.get_task("task:ingest:123")

    assert task == {
        "task_id": "task:ingest:123",
        "type": "ingest",
        "status": "processing",
        "meta": {"files": ["law.pdf"]},
        "error": "",
    }
