from settings import QDRANT_URL, QDRANT_API_KEY
from qdrant_client import QdrantClient

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)
print ("✅ Qdrant client configured successfully.")
print (f"QDRANT_URL: {QDRANT_URL}")