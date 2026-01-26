import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

load_dotenv()

client = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ["QDRANT_API_KEY"]
)

COLLECTION = "biocup_hybrid_splade_v1"

DENSE_DIM = 768  # bge-base/e5-base

if not client.collection_exists(COLLECTION):
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={
            "dense": qm.VectorParams(size=DENSE_DIM, distance=qm.Distance.COSINE),  #pour le sens global
        },
        sparse_vectors_config={     # pour les termes exactes
            "sparse": qm.SparseVectorParams(modifier=qm.Modifier.IDF)  # IDF côté serveur :contentReference[oaicite:6]{index=6}
        },
        hnsw_config=qm.HnswConfigDiff(m=16, ef_construct=256),
        optimizers_config=qm.OptimizersConfigDiff(indexing_threshold=20000),
    )
    print("✅ Created collection:", COLLECTION)
else:
    print("ℹ️ Collection already exists:", COLLECTION)
