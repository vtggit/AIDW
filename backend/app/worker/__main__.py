"""``python -m app.worker`` — the connector/ingestion worker process (operator-deployed)."""

from app.observability.logging import setup_logging
from app.worker.loop import main_loop

if __name__ == "__main__":
    setup_logging()
    main_loop()
