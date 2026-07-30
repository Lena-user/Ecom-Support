"""Khởi tạo Qdrant: Tạo collections và đưa MOCK_KB vào dạng Vector Embedding."""

import logging
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from app.config import settings
from app.llm import get_embedding
from app.graph.nodes import MOCK_KB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db():
    logger.info(f"Connecting to Qdrant at {settings.qdrant_host}:{settings.qdrant_port}...")
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

    # Khởi tạo collection "knowledge_base" (RAG)
    kb_col = "knowledge_base"
    logger.info(f"Recreating collection '{kb_col}'...")
    if client.collection_exists(kb_col):
        client.delete_collection(kb_col)
    
    client.create_collection(
        collection_name=kb_col,
        vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
    )

    # Nhập MOCK_KB vào "knowledge_base"
    logger.info(f"Ingesting {len(MOCK_KB)} documents into '{kb_col}'...")
    points = []
    for i, doc in enumerate(MOCK_KB):
        text_to_embed = f"{doc['source']}: {doc['content']}"
        vector = get_embedding(text_to_embed)
        points.append(
            PointStruct(
                id=i + 1,
                vector=vector,
                payload={
                    "id": doc["id"],
                    "source": doc["source"],
                    "content": doc["content"],
                }
            )
        )
    
    client.upsert(collection_name=kb_col, points=points)
    logger.info("Successfully ingested knowledge base!")

    # Khởi tạo collection "tickets" (Duplicate Check)
    ticket_col = "tickets"
    logger.info(f"Recreating collection '{ticket_col}'...")
    if client.collection_exists(ticket_col):
        client.delete_collection(ticket_col)
    
    client.create_collection(
        collection_name=ticket_col,
        vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
    )
    logger.info("Successfully created 'tickets' collection!")


if __name__ == "__main__":
    init_db()
