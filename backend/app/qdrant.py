"""Qdrant client singleton."""

from qdrant_client import QdrantClient
from app.config import settings

_qdrant_client: QdrantClient | None = None

def get_qdrant() -> QdrantClient:
    """Lazy init Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
    return _qdrant_client
