import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app import rq_worker


class FakeWorker:
    def __init__(self, queues, connection):
        self.queues = queues
        self.connection = connection

    def work(self, with_scheduler=False):
        assert with_scheduler is True


def test_worker_initializes_ai_and_enables_scheduler(monkeypatch):
    calls = []
    connection = object()

    monkeypatch.setattr(rq_worker, "initialize_worker_ai", lambda: calls.append("ai"))
    monkeypatch.setattr(rq_worker, "get_rq_redis_client", lambda: connection)
    monkeypatch.setattr(rq_worker, "Queue", lambda name, connection: ("queue", name, connection))
    monkeypatch.setattr(rq_worker, "SimpleWorker", FakeWorker)

    rq_worker.main()

    assert calls == ["ai"]
