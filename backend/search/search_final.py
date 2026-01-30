# backend/search/search_final.py
# ============================================================
# BioCUP — Robust Hybrid Search (Qdrant payloads + CSV text join)
# ============================================================

import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

load_dotenv(dotenv_path=ROOT / ".env", override=True)

COLLECTION = os.getenv("COLLECTION_NAME", "biocup_hybrid_splade_v1")

INPUT_EMB_DIR = ROOT / "data" / "input" / "embeddings"
META_PATH = INPUT_EMB_DIR / "meta.parquet"
DENSE_PATH = INPUT_EMB_DIR / "dense.npy"
SPARSE_PATH = INPUT_EMB_DIR / "sparse_splade.npz"

# 🔑 Where real text lives
CHUNKS_CSV = ROOT / "data" / "processed" / "biocup_chunks.csv"

# ------------------------------------------------------------
# Parameters
# ------------------------------------------------------------
K_DENSE = 80
K_SPARSE = 80
K_FUSED = 50
RRF_K = 60

MAX_CASES_PER_INPUT_CHUNK = 15
MAX_EVIDENCE_PER_SITE = 6
CONSISTENCY_BONUS = 0.20

SECTION_WEIGHT = {
    "IHC": 2.4,
    "DIAGNOSIS": 2.0,
    "SYNOPTIC": 1.5,
    "LYMPH_NODES": 1.2,
    "MARGINS": 1.1,
    "GENERAL": 0.7,
    "COMMENT": 0.6,
}

def w_section(sec: str) -> float:
    return SECTION_WEIGHT.get((sec or "GENERAL").upper(), 1.0)

def is_strong_section(sec) -> bool:
    return str(sec).upper() in ("IHC", "DIAGNOSIS", "SYNOPTIC")

# ------------------------------------------------------------
# Qdrant
# ------------------------------------------------------------
client = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ.get("QDRANT_API_KEY"),
)

# ------------------------------------------------------------
# Load chunk text once (FAST)
# ------------------------------------------------------------
_chunks_df = pd.read_csv(CHUNKS_CSV)

# adapt column names safely
TEXT_COL = "chunk_text" if "chunk_text" in _chunks_df.columns else "text"
ID_COL = "chunk_id_raw" if "chunk_id_raw" in _chunks_df.columns else "chunk_id"

CHUNK_TEXT = dict(
    zip(
        _chunks_df[ID_COL].astype(str),
        _chunks_df[TEXT_COL].astype(str)
    )
)

# ------------------------------------------------------------
# Filters
# ------------------------------------------------------------
def section_must_any(values):
    return qm.FieldCondition(key="section", match=qm.MatchAny(any=values))

def build_filter(input_section: str):
    sec = (input_section or "GENERAL").upper()
    must = []
    must_not = [qm.FieldCondition(key="is_admin_noise", match=qm.MatchValue(value=1))]

    if sec == "IHC":
        must += [
            section_must_any(["IHC", "DIAGNOSIS"]),
            qm.FieldCondition(key="has_ihc", match=qm.MatchValue(value=True))
        ]
    else:
        must.append(section_must_any(["DIAGNOSIS", "SYNOPTIC", "IHC"]))

    return qm.Filter(must=must, must_not=must_not)

# ------------------------------------------------------------
# RRF fusion
# ------------------------------------------------------------
def rrf_fuse(dense_pts, sparse_pts, k=RRF_K):
    score = defaultdict(float)
    payload = {}

    for rank, p in enumerate(dense_pts):
        score[p.id] += 1 / (k + rank + 1)
        payload.setdefault(p.id, p.payload)

    for rank, p in enumerate(sparse_pts):
        score[p.id] += 1 / (k + rank + 1)
        payload.setdefault(p.id, p.payload)

    ids = sorted(score, key=score.get, reverse=True)
    return ids, score, payload

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def predict_primary_site():
    meta = pd.read_parquet(META_PATH)
    dense = np.load(DENSE_PATH)
    sp = np.load(SPARSE_PATH, allow_pickle=True)

    N = len(meta)

    case_score = defaultdict(float)
    case_chunks = defaultdict(set)
    case_payload = {}
    case_site = {}

    for i in range(N):
        sec = meta.iloc[i].get("section", "GENERAL")
        flt = build_filter(sec)

        d = client.query_points(
            COLLECTION, dense[i].tolist(),
            using="dense", limit=K_DENSE,
            query_filter=flt, with_payload=True
        ).points or []

        s = client.query_points(
            COLLECTION,
            qm.SparseVector(
                indices=sp["indices"][i].tolist(),
                values=sp["values"][i].tolist(),
            ),
            using="sparse", limit=K_SPARSE,
            query_filter=flt, with_payload=True
        ).points or []

        fused, scores, payloads = rrf_fuse(d, s)

        per_case = {}
        for pid in fused[:K_FUSED]:
            pl = payloads.get(pid)
            if not pl:
                continue
            cid = pl.get("case_id")
            site = pl.get("primary_site")
            if not cid or not site:
                continue

            sc = scores[pid] * w_section(sec)
            if sc > per_case.get(cid, 0):
                per_case[cid] = sc
                case_payload[cid] = pl
                case_site[cid] = site

        for cid, sc in sorted(per_case.items(), key=lambda x: x[1], reverse=True)[:MAX_CASES_PER_INPUT_CHUNK]:
            case_score[cid] += sc
            case_chunks[cid].add(i)

    # consistency bonus
    final_case_score = {}
    for cid, sc in case_score.items():
        bonus = 1 + CONSISTENCY_BONUS * (len(case_chunks[cid]) - 1)
        final_case_score[cid] = sc * bonus

    # aggregate by site
    site_score = defaultdict(float)
    for cid, sc in final_case_score.items():
        site_score[case_site[cid]] += sc

    # evidence
    evidence = defaultdict(list)
    for cid, sc in final_case_score.items():
        pl = case_payload[cid]
        raw_id = pl.get("chunk_id_raw")
        text = CHUNK_TEXT.get(str(raw_id), "")
        snippet = text[:220] + "..." if len(text) > 220 else text

        evidence[case_site[cid]].append({
            "case_id": cid,
            "score": float(sc),
            "section": pl.get("section"),
            "snippet": snippet,
            "chunk_id_raw": raw_id,
        })

    for site in evidence:
        evidence[site] = sorted(evidence[site], key=lambda x: x["score"], reverse=True)[:MAX_EVIDENCE_PER_SITE]

    total = sum(site_score.values())
    pct = {s: v / total * 100 for s, v in site_score.items()} if total else {}
    sorted_sites = sorted(pct.items(), key=lambda x: x[1], reverse=True)

    return pct, {
        "sorted_sites": sorted_sites,
        "evidence": dict(evidence),
        "n_input_chunks": N,
    }

# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------
if __name__ == "__main__":
    info = client.get_collection(COLLECTION)
    print(f"Collection OK — points: {info.points_count}\n")

    pct, dbg = predict_primary_site()

    print("Predicted primary sites:")
    for s, p in dbg["sorted_sites"]:
        print(f"{s:12s} {p:6.2f}%")

    for s, _ in dbg["sorted_sites"][:3]:
        print(f"\n--- {s} ---")
        for e in dbg["evidence"][s]:
            print(f"{e['case_id']} | {e['section']} | {e['snippet']}")
