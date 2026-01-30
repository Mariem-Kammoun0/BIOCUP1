# backend/embedding/dense.py
import numpy as np
import pandas as pd
from pathlib import Path
from sentence_transformers import SentenceTransformer


# =========================
# PATHS / CONFIG
# =========================
CSV_PATH = Path("../../data/input/chunks/input_chunks.csv")
OUT_DIR = Path("../../data/input/embeddings")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TEXT_COL = "chunk_text"
ID_COL = "chunk_id"

# Dense model (high quality)
DENSE_MODEL = "BAAI/bge-base-en-v1.5"  # ou: "intfloat/e5-base-v2"
BATCH_SIZE = 64


# =========================
# LOAD + CLEAN
# =========================
df = pd.read_csv(CSV_PATH)

# assurer que chunk_text existe
if TEXT_COL not in df.columns:
    raise ValueError(f"Missing column: {TEXT_COL}")

df[TEXT_COL] = df[TEXT_COL].astype(str).fillna("")
df = df[df[TEXT_COL].str.strip().ne("")].reset_index(drop=True)

# garder toutes les colonnes importantes pour payload + traçabilité
META_COLS = [
    "chunk_id",
    "case_id",
    "primary_site",
    "tcga_type",
    "patient_id",
    "section",
    "original_section",
    "chunk_index",
    "sub_index",
    "has_tnm",
    "has_size",
    "has_ihc",
    "has_lymph",
    "has_margins",
    "has_tumor_size_cue",
    "is_admin_noise",
]

missing = [c for c in META_COLS if c not in df.columns]
if missing:
    raise ValueError(f"Missing columns in CSV: {missing}")

meta = df[META_COLS].copy()
texts = df[TEXT_COL].tolist()

print(f" Loaded chunks: {len(df)}")


# =========================
# DENSE EMBEDDINGS
# =========================
model = SentenceTransformer(DENSE_MODEL)

dense_vecs = model.encode(
    texts,
    batch_size=BATCH_SIZE,
    show_progress_bar=True,
    normalize_embeddings=True,  # recommandé avec COSINE
)

dense_vecs = dense_vecs.astype("float32")


# =========================
# SAVE
# =========================
np.save(OUT_DIR / "dense.npy", dense_vecs)
meta.to_parquet(OUT_DIR / "meta.parquet", index=False)

print(" Dense saved:", OUT_DIR / "dense.npy")
print(" Meta saved:", OUT_DIR / "meta.parquet")
print("Dense shape:", dense_vecs.shape)
