from qdrant_client import QdrantClient, models
import os

client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))

# Quick health check
collections = client.get_collections()
print(f"Connected to Qdrant Cloud: {len(collections.collections)} collections")