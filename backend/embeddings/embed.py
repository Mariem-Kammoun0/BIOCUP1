import pandas as pd
from pathlib import Path

CSV_PATH = "../data/ihc.csv"   
BASE_DIR = ".."               

df = pd.read_csv(CSV_PATH)

def load_image_rgb(path: Path) -> Image.Image:
    """Load an image from disk and convert to RGB (PIL)."""
    img = Image.open(path)
    return img.convert("RGB")

def resolve_path(p: str) -> Path:
    p = str(p).strip().replace("\\", "/")
    path = Path(p)
    if not path.is_absolute():
        path = Path(BASE_DIR) / path
    return path

df["_resolved_path"] = df["image_path"].apply(resolve_path)

df_ok = df[df["_resolved_path"].apply(lambda p: p.exists())].copy()
print("Ready rows:", len(df_ok))

CANON_CANCER = {
    "lungs": "lung",
    "lung": "lung",
    "breast": "breast",
    "colon": "colon",
    "pancreas": "pancreas",
    "liver": "liver",
    "ovary": "ovary",
    "prostate": "prostate",
}

df_ok["cancer"] = df_ok["cancer"].astype(str).str.strip().str.lower().map(lambda x: CANON_CANCER.get(x, x))
df_ok["tissue_state"] = df_ok["tissue_state"].astype(str).str.strip().str.lower()
df_ok["modality"] = df_ok["modality"].astype(str).str.strip().str.upper()
df_ok["source"] = df_ok["source"].astype(str).str.strip()

def build_payload(row):
    payload = {
        "cancer": row["cancer"],
        "tissue_state": row["tissue_state"],   # tumor / normal
        "source": row["source"],               # HPA
        "modality": row["modality"],           # IHC
    }

  
    gene = str(row.get("gene_symbol", "")).strip()
    ihc  = str(row.get("ihc_name", "")).strip()

    if gene.upper() not in {"", "NA", "NONE", "NAN"}:
        payload["gene_symbol"] = gene
    if ihc.upper() not in {"", "NA", "NONE", "NAN"}:
        payload["ihc_name"] = ihc

    return payload
