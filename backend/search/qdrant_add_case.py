# backend/search/qdrant_add_case.py
import os
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)

QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION = os.getenv("COLLECTION_NAME", "biocup_hybrid_splade_v1")

client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def _collection_has_sparse() -> bool:
    info = client.get_collection(COLLECTION)
    sparse_cfg = getattr(info.config.params, "sparse_vectors", None)
    return bool(sparse_cfg)


def upsert_validated_case(
    case_id: str,
    primary_site: str,
    chunks: List[Dict[str, Any]],
    dense_vectors: np.ndarray,
    sparse_indices: Optional[List[np.ndarray]] = None,
    sparse_values: Optional[List[np.ndarray]] = None,
) -> Dict[str, Any]:
    """
    chunks: list of payload chunks with 'section' and 'chunk_text' etc.
    dense_vectors: (N, dim) float32
    sparse_indices/values: ragged lists (optional) if collection has sparse
    """
    use_sparse = _collection_has_sparse()

    if use_sparse and (sparse_indices is None or sparse_values is None):
        raise ValueError("Collection supports sparse vectors, but sparse vectors were not provided.")

    points = []
    for i, ch in enumerate(chunks):
        payload = dict(ch)
        payload.update({
            "case_id": case_id,
            "primary_site": primary_site,
            "source": "user_validated",
            "chunk_index": int(payload.get("chunk_index", i)),
        })

        vecs = {"dense": dense_vectors[i].tolist()}

        if use_sparse:
            sv = qm.SparseVector(
                indices=sparse_indices[i].tolist(),
                values=sparse_values[i].tolist(),
            )
            vecs["sparse"] = sv

        points.append(
            qm.PointStruct(
                id=str(uuid.uuid4()),
                vector=vecs,
                payload=payload,
            )
        )

    client.upsert(collection_name=COLLECTION, points=points)
    return {"upserted_points": len(points), "collection": COLLECTION}
