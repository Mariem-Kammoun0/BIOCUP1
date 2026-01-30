# backend/embedding/sparse.py
import numpy as np
import pandas as pd
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForMaskedLM


# =========================
# PATHS / CONFIG
# =========================
CSV_PATH = Path("../../data/input/chunks/input_chunks.csv")
OUT_DIR = Path("../../data/input/embeddings")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TEXT_COL = "chunk_text"

# Sparse model (SPLADE++)
SPLADE_MODEL = "prithivida/Splade_PP_en_v1"
BATCH_SIZE = 16
MAX_LENGTH = 128
TOPK = 256


# =========================
# LOAD + CLEAN
# =========================
df = pd.read_csv(CSV_PATH)

if TEXT_COL not in df.columns:
    raise ValueError(f"Missing column: {TEXT_COL}")

df[TEXT_COL] = df[TEXT_COL].astype(str).fillna("")
df = df[df[TEXT_COL].str.strip().ne("")].reset_index(drop=True)

texts = df[TEXT_COL].tolist()

print(f"✅ Loaded chunks: {len(df)}")


# =========================
# LOAD SPLADE
# =========================
device = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(SPLADE_MODEL)
splade = AutoModelForMaskedLM.from_pretrained(
    SPLADE_MODEL,
    use_safetensors=True
).to(device).eval()



@torch.no_grad()
def splade_encode(texts):
    """
    Retourne 2 listes (ragged):
      - indices[i] = array d'indices vocab (token ids) les plus importants pour le texte i
      - values[i]  = array de poids correspondants (float)
    SPLADE: weights = max_{tokens}( log(1 + relu(logits)) )
    """
    all_indices = []
    all_values = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]

        enc = tok(
            batch,
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors="pt"
        ).to(device)

        logits = splade(**enc).logits               # (B, L, V)
        weights = torch.log1p(torch.relu(logits))   # (B, L, V)
        weights = weights.max(dim=1).values         # (B, V)

        weights = weights.cpu()

        for w in weights:
            nz = torch.nonzero(w).squeeze(-1)   # indices non-nuls
            vals = w[nz]

            # top-k pour réduire la taille des sparse vectors
            if nz.numel() > TOPK:
                vals, idx = torch.topk(vals, k=TOPK)
                nz = nz[idx]

            all_indices.append(nz.numpy().astype(np.int32))
            all_values.append(vals.numpy().astype(np.float32))

    return all_indices, all_values


indices, values = splade_encode(texts)

# =========================
# SAVE (ragged arrays)
# =========================
np.savez_compressed(
    OUT_DIR / "sparse_splade.npz",
    indices=np.array(indices, dtype=object),
    values=np.array(values, dtype=object),
)

print("✅ Sparse saved:", OUT_DIR / "sparse_splade.npz")
print("Chunks:", len(indices))