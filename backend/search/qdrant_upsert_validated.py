# backend/search/qdrant_upsert_validated.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm


def upsert_validated_input_case(
    collection_name: str,
    patient_case_id: str,
    predicted_primary_site: str,
    embeddings_dir: Path,
    chunks_csv: Path,
    url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Upserts the CURRENT input case chunks (from data/input/chunks/input_chunks.csv)
    using embeddings already built in embeddings_dir.

    REQUIREMENTS:
    - dense.npy  shape (N, dim)
    - sparse_splade.npz with arrays: indices, values
    - meta.parquet with N rows
    - input_chunks.csv containing chunk_text + section + chunk_index (at least)
    """

    client = QdrantClient(url=url, api_key=api_key) if url else QdrantClient()

    dense = np.load(embeddings_dir / "dense.npy").astype("float32")
    meta = pd.read_parquet(embeddings_dir / "meta.parquet")

    sp = np.load(embeddings_dir / "sparse_splade.npz", allow_pickle=True)
    sp_indices = sp["indices"]
    sp_values = sp["values"]

    chunks_df = pd.read_csv(chunks_csv)

    # Map: chunk_index -> chunk_text (safe)
    chunk_text_map = {}
    if "chunk_index" in chunks_df.columns and "chunk_text" in chunks_df.columns:
        for _, r in chunks_df.iterrows():
            chunk_text_map[int(r["chunk_index"])] = str(r["chunk_text"]) if not pd.isna(r["chunk_text"]) else ""

    points = []
    for i, row in meta.iterrows():
        chunk_index = int(row.get("chunk_index", i))

        payload = {
            "case_id": patient_case_id,
            "primary_site": predicted_primary_site,
            "section": row.get("section"),
            "chunk_index": chunk_index,
            "sub_index": int(row.get("sub_index", 0)),
            "chunk_id_raw": row.get("chunk_id_raw") or f"{patient_case_id}|{row.get('section')}|{chunk_index}",
            "chunk_text": chunk_text_map.get(chunk_index, ""),  # ✅ THIS FIXES SNIPPETS
            "is_admin_noise": int(row.get("is_admin_noise", 0)),
            "has_ihc": bool(row.get("has_ihc", 0)),
            "has_lymph": bool(row.get("has_lymph", 0)),
            "has_margins": bool(row.get("has_margins", 0)),
            "has_tnm": bool(row.get("has_tnm", 0)),
            "has_size": bool(row.get("has_size", 0)),
        }

        vec_dense = dense[i]
        vec_sparse = qm.SparseVector(
            indices=list(sp_indices[i]),
            values=list(sp_values[i]),
        )

        points.append(
            qm.PointStruct(
                id=f"{patient_case_id}_{i}",
                vector={"dense": vec_dense, "sparse": vec_sparse},
                payload=payload,
            )
        )

    client.upsert(
        collection_name=collection_name,
        points=points,
        wait=True,
    )

    return {
        "status": "ok",
        "collection": collection_name,
        "case_id": patient_case_id,
        "n_points": len(points),
        "primary_site": predicted_primary_site,
    }
