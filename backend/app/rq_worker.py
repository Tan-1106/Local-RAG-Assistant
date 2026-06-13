from rq                 import Queue, SimpleWorker
from app.config         import settings
from app.logger         import get_logger
from app.db.redis_store import get_rq_redis_client

logger = get_logger(__name__)


def initialize_worker_ai() -> None:
    from app.services.ai_logic import initialize_ai

    initialize_ai()


def main() -> None:
    """Initialize the AI stack once, then process RQ jobs in the same process."""
    logger.info("Initializing AI stack for the document-ingestion worker")
    initialize_worker_ai()

    connection = get_rq_redis_client()
    queue = Queue(settings.RQ_QUEUE_NAME, connection=connection)
    worker = SimpleWorker([queue], connection=connection)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
