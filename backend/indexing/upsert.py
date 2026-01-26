# backend/qdrant/upsert.py

import os
import uuid
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm


# =========================
# CONFIG
# =========================
load_dotenv()

COLLECTION = "biocup_hybrid_splade_v1"

EMB_DIR = Path("../../data/embeddings")
META_PATH = EMB_DIR / "meta.parquet"
DENSE_PATH = EMB_DIR / "dense.npy"
SPARSE_PATH = EMB_DIR / "sparse_splade.npz"

BATCH_SIZE = 128


# =========================
# QDRANT CLIENT
# =========================
client = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ.get("QDRANT_API_KEY"),
)


# =========================
# UTILS
# =========================
def stable_uuid(text: str) -> str:
    """UUID stable et valide pour Qdrant"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, text))


def payload_safe(d: dict) -> dict:
    """Convertit NaN → None + types JSON-safe"""
    out = {}
    for k, v in d.items():
        if pd.isna(v):
            out[k] = None
        elif isinstance(v, (np.integer,)):
            out[k] = int(v)
        elif isinstance(v, (np.floating,)):
            out[k] = float(v)
        else:
            out[k] = v
    return out


# =========================
# LOAD DATA
# =========================
print("📥 Loading data...")

meta = pd.read_parquet(META_PATH)
dense = np.load(DENSE_PATH)
sp = np.load(SPARSE_PATH, allow_pickle=True)
sp_indices = sp["indices"]
sp_values = sp["values"]

N = len(meta)

assert dense.shape[0] == N == len(sp_indices) == len(sp_values), "❌ Data misalignment"

print(f"✅ Loaded {N} points")


# =========================
# UPSERT
# =========================
print("🚀 Upserting into Qdrant...")

for start in range(0, N, BATCH_SIZE):
    end = min(start + BATCH_SIZE, N)
    points = []

    for i in range(start, end):
        row = meta.iloc[i]
        raw_id = str(row["chunk_id"])
        pid = stable_uuid(raw_id)

        sv = qm.SparseVector(
            indices=sp_indices[i].tolist(),
            values=sp_values[i].tolist(),
        )

        payload = payload_safe(row.to_dict())
        payload["chunk_id_raw"] = raw_id  # traçabilité

        points.append(
            qm.PointStruct(
                id=pid,
                vector={
                    "dense": dense[i].tolist(),
                    "sparse": sv,
                },
                payload=payload,
            )
        )

    client.upsert(collection_name=COLLECTION, points=points)
    print(f"✅ Upserted {end}/{N}")

print("🎉 DONE — All points uploaded to Qdrant")
