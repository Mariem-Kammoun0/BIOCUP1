import json
import re
from qdrant_client.http import models as qm
import numpy as np
import pandas as pd
from pathlib import Path
from PIL import Image
from qdrant_client.http.models import PointStruct

from backend.config.settings import (
    CSV_PATH, IMAGES_ROOT, BATCH_SIZE, COLLECTION_NAME, CANON_CANCER
)
from backend.config.qdrant import get_qdrant_client
from backend.embeddings.embed_image import embed_image

def to_int_id(image_id: str) -> int:
    """
    Convert 'img_001' -> 1, 'img_214' -> 214
    """
    m = re.search(r"\d+", str(image_id))
    if not m:
        raise ValueError(f"Invalid image_id (no digits): {image_id}")
    return int(m.group(0))


def load_image(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def build_payload(row: pd.Series) -> dict:
    payload = {
        "cancer": row["cancer"],
        "tissue_state": row["tissue_state"],
        "source": row["source"],
        "modality": row["modality"],
    }


    if pd.notna(row.get("gene_symbol", None)):
        payload["gene_symbol"] = row["gene_symbol"]

    if pd.notna(row.get("ihc_name", None)):
        payload["ihc_name"] = row["ihc_name"]

    return payload


def main():
    print("🔹 Loading CSV:", CSV_PATH)
    df = pd.read_csv(CSV_PATH)

    # Normalize
    df["cancer"] = (
        df["cancer"].astype(str).str.lower().map(lambda x: CANON_CANCER.get(x, x))
    )
    df["tissue_state"] = df["tissue_state"].str.lower()
    df["modality"] = df["modality"].str.upper()

    # Resolve paths
    df["image_path"] = df["image_path"].astype(str).str.replace("\\", "/")
    df["_path"] = df["image_path"].apply(lambda p: (IMAGES_ROOT / p).resolve())

    df = df[df["_path"].apply(lambda p: p.exists())].copy()
    print("✅ Images found:", len(df))

    # Qdrant
    client = get_qdrant_client()

    # Infer embedding dim
    test_vec = embed_image(load_image(df.iloc[0]["_path"]))
    dim = test_vec.shape[0]
    print("Embedding dim:", dim)

    # Create collection if missing
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        )
        print(f"✅ Created collection: {COLLECTION_NAME}")
    else:
        print(f"✅ Collection exists: {COLLECTION_NAME}")

    # Upsert
    for i in range(0, len(df), BATCH_SIZE):
        batch = df.iloc[i:i+BATCH_SIZE]
        points = []

        for _, r in batch.iterrows():
            vec = embed_image(load_image(r["_path"]))
            payload = build_payload(r)
            pid = to_int_id(r["image_id"])
            points.append(
                PointStruct(
                    id=pid,
                    vector=vec.tolist(),
                    payload=payload
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"⬆️ Upserted {i + len(batch)}/{len(df)}")

    print("🎉 DONE — dataset indexed in Qdrant")


if __name__ == "__main__":
    main()
