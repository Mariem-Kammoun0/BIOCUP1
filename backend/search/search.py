# backend/search/search_final.py
# ============================================================
# BioCUP — Robust Hybrid Search (INPUT chunks -> Qdrant -> % primary_site)
#
# Key ideas:
# 1) Each BioCUP CASE has MANY chunks stored in Qdrant (DIAGNOSIS/IHC/LYMPH...).
#    => We must avoid counting multiple chunks of the SAME case as multiple votes.
# 2) Each INPUT patient has MANY chunks too.
#    => If the SAME case is retrieved by MULTIPLE input chunks, that's stronger evidence.
#
# Pipeline per input chunk:
#   dense search + sparse search -> RRF fusion -> best score per case for this chunk
#
# Aggregation across input chunks:
#   case_score = SUM(best_score_for_case_in_each_input_chunk) * (1 + bonus*(support_chunks-1))
#   primary_site score = SUM(case_score for cases of that site)
# ============================================================

import os
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
import sys
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[2]  # BIOCUP1
sys.path.append(str(ROOT))


# =========================
# CONFIG
# =========================
load_dotenv()

COLLECTION = "biocup_hybrid_splade_v1"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_EMB_DIR = PROJECT_ROOT / "data" / "input" / "embeddings"

META_PATH = INPUT_EMB_DIR / "meta.parquet"  # or meta.csv
DENSE_PATH = INPUT_EMB_DIR / "dense.npy"
SPARSE_PATH = INPUT_EMB_DIR / "sparse_splade.npz"

# Retrieval sizes (per input chunk)
K_DENSE = 80
K_SPARSE = 80
K_FUSED = 50

# Fusion parameter
RRF_K = 60

# To prevent dilution: per input chunk, keep only top cases
MAX_CASES_PER_INPUT_CHUNK = 15

# Evidence per predicted site
MAX_EVIDENCE_PER_SITE = 6

# Consistency bonus: if same case is supported by many input chunks
CONSISTENCY_BONUS = 0.20  # +20% per extra input chunk supporting that case

# Section weights (importance)
SECTION_WEIGHT = {
    "IHC": 2.4,
    "DIAGNOSIS": 2.0,
    "SYNOPTIC": 1.5,
    "LYMPH_NODES": 1.2,
    "MARGINS": 1.1,
    "MICRO": 0.7,
    "GROSS": 0.5,
    "SPECIMEN": 0.3,
    "GENERAL": 0.7,
    "COMMENT": 0.6,
}

def w_section(section: str) -> float:
    return SECTION_WEIGHT.get((section or "GENERAL").upper(), 1.0)



GENERIC_PATTERNS = [
    # negativity / margins
    "negative for malignancy",
    "no tumor seen",
    "free of tumor",
    "margins negative",
    "resection margins negative",

    # lymph nodes
    "lymph nodes negative",
    "no lymph node metastasis",
    "n0",
    "pno",

    # size / staging
    "tumor size",
    "greatest dimension",
    "pt", "pn", "pm",
    "pathologic staging",
    "tnm",

    # procedural / non-discriminant
    "specimen received",
    "submitted in toto",
    "gross description",
]



STRONG_PATTERNS = [
    # Lung
    "ttf-1", "napsin a",

    # Colon / GI
    "cdx2", "ck20", "satb2",

    # Breast
    "er", "pr", "her2", "gata3",

    # Prostate
    "psa", "psap", "nkx3.1",

    # Gynecologic / ovary
    "pax8", "wt1",

    # Liver
    "heppar-1", "arg1",

    # General epithelial
    "ck7", "ck5/6", "p63",
]



def clinical_quality_boost(payload: dict) -> float:
    """
    Returns a multiplicative factor:
    > 1.0 => boost (discriminative chunks)
    < 1.0 => penalty (generic chunks)
    """
    sec = str(payload.get("section", "")).upper()
    txt = str(payload.get("chunk_text", "")).lower()

    boost = 1.0

    # Strong sections boost
    if sec in ("IHC", "DIAGNOSIS", "SYNOPTIC"):
        boost *= 1.15
    elif sec in ("GROSS", "MICRO", "SPECIMEN"):
        boost *= 0.90

    # Penalize generic content
    generic_hits = sum(1 for p in GENERIC_PATTERNS if p in txt)
    boost *= (0.92 ** generic_hits)

    # Boost strong markers
    strong_hits = sum(1 for p in STRONG_PATTERNS if p in txt)
    boost *= (1.06 ** strong_hits)

    return float(boost)

def is_strong_section(sec) -> bool:
    return str(sec).upper() in ("IHC", "DIAGNOSIS", "SYNOPTIC")

# =========================
# QDRANT CLIENT
# =========================
client = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ.get("QDRANT_API_KEY"),
)

# =========================
# IO
# =========================
def read_meta(path: Path) -> pd.DataFrame:
    if str(path).endswith(".parquet"):
        return pd.read_parquet(path)
    return pd.read_csv(path)

# =========================
# FILTERS
# =========================
def section_must_any(section_values):
    return qm.FieldCondition(key="section", match=qm.MatchAny(any=section_values))

def build_filter_for_input_chunk(input_section: str) -> qm.Filter:
    sec = (input_section or "GENERAL").upper()

    must = []
    must_not = [qm.FieldCondition(key="is_admin_noise", match=qm.MatchValue(value=1))]

    if sec == "IHC":
        must.append(section_must_any(["IHC", "DIAGNOSIS"]))
        must.append(qm.FieldCondition(key="has_ihc", match=qm.MatchValue(value=True)))

    elif sec in ("LYMPH_NODES", "LYMPH"):
        must.append(section_must_any(["LYMPH_NODES", "SYNOPTIC", "DIAGNOSIS"]))
        must.append(qm.FieldCondition(key="has_lymph", match=qm.MatchValue(value=True)))

    elif sec == "MARGINS":
        must.append(section_must_any(["MARGINS", "SYNOPTIC", "DIAGNOSIS"]))
        must.append(qm.FieldCondition(key="has_margins", match=qm.MatchValue(value=True)))

    elif sec == "SYNOPTIC":
        must.append(section_must_any(["SYNOPTIC", "DIAGNOSIS", "MARGINS", "LYMPH_NODES"]))

    elif sec == "DIAGNOSIS":
        must.append(section_must_any(["DIAGNOSIS", "SYNOPTIC"]))

    else:
        must.append(section_must_any(["DIAGNOSIS", "SYNOPTIC", "IHC", "LYMPH_NODES", "MARGINS"]))

    return qm.Filter(must=must, must_not=must_not)

# =========================
# RRF FUSION
# =========================
def rrf_fuse(dense_points, sparse_points, k=RRF_K):
    id2score = {}
    id2payload = {}

    for rank, p in enumerate(dense_points):
        pid = p.id
        id2score[pid] = id2score.get(pid, 0.0) + 1.0 / (k + rank + 1)
        if pid not in id2payload and p.payload:
            id2payload[pid] = p.payload

    for rank, p in enumerate(sparse_points):
        pid = p.id
        id2score[pid] = id2score.get(pid, 0.0) + 1.0 / (k + rank + 1)
        if pid not in id2payload and p.payload:
            id2payload[pid] = p.payload

    fused = sorted(id2score.items(), key=lambda x: x[1], reverse=True)
    fused_ids = [pid for pid, _ in fused]
    return fused_ids, id2score, id2payload

# =========================
# MAIN
# =========================
def predict_primary_site():
    # Load input embeddings
    meta = read_meta(META_PATH)
    dense = np.load(DENSE_PATH)
    sp = np.load(SPARSE_PATH, allow_pickle=True)
    sp_indices, sp_values = sp["indices"], sp["values"]

    N = len(meta)
    assert dense.shape[0] == N == len(sp_indices) == len(sp_values), "❌ Input files misaligned"

    # ---- Case-level aggregation across all input chunks
    case_total_score = defaultdict(float)          # case_id -> sum best contrib across chunks
    case_supported_by_chunks = defaultdict(set)    # case_id -> {chunk_i}
    case_best_payload = {}                         # case_id -> payload (best contrib)
    case_best_score = defaultdict(float)           # case_id -> best contrib
    case_site = {}                                 # case_id -> primary_site

    # -----------------------------
    # For EACH INPUT chunk:
    #   1) query dense
    #   2) query sparse
    #   3) fuse
    #   4) reduce to BEST per case for this chunk
    # -----------------------------
    for i in range(N):
        row = meta.iloc[i]
        input_section = str(row.get("section", "GENERAL"))
        sec_w = w_section(input_section)

        q_dense = dense[i].tolist()
        q_sparse = qm.SparseVector(
            indices=sp_indices[i].tolist(),
            values=sp_values[i].tolist()
        )
        flt = build_filter_for_input_chunk(input_section)

        # ---- Dense
        dense_res = client.query_points(
            collection_name=COLLECTION,
            query=q_dense,
            using="dense",
            query_filter=flt,
            limit=K_DENSE,
            with_payload=True
        )
        dense_pts = dense_res.points or []

        # ---- Sparse
        sparse_res = client.query_points(
            collection_name=COLLECTION,
            query=q_sparse,
            using="sparse",
            query_filter=flt,
            limit=K_SPARSE,
            with_payload=True
        )
        sparse_pts = sparse_res.points or []

        # ---- Fuse (RRF)
        fused_ids, id2rrf, id2payload = rrf_fuse(dense_pts, sparse_pts, k=RRF_K)
        fused_ids = fused_ids[:K_FUSED]

        # ---- Reduce: keep BEST score per CASE for this input chunk
        best_case_this_chunk = {}       # case_id -> best contrib
        best_payload_this_chunk = {}    # case_id -> payload of best contrib

        for pid in fused_ids:
            payload = id2payload.get(pid)
            if not payload:
                continue

            site = payload.get("primary_site")
            case_id = payload.get("case_id")
            if not site or not case_id:
                continue

            cid = str(case_id)
            contrib = float(id2rrf.get(pid, 0.0)) * float(sec_w)

            if contrib > best_case_this_chunk.get(cid, 0.0):
                best_case_this_chunk[cid] = contrib
                best_payload_this_chunk[cid] = payload

        # ---- Keep only top cases per input chunk (avoid dilution)
        top_cases = sorted(best_case_this_chunk.items(), key=lambda x: x[1], reverse=True)[:MAX_CASES_PER_INPUT_CHUNK]

        for cid, contrib in top_cases:
            payload = best_payload_this_chunk.get(cid, {})

            # register support
            case_supported_by_chunks[cid].add(i)

            # sum contributions across chunks
            case_total_score[cid] += contrib

            # save site mapping
            site = payload.get("primary_site")
            if site:
                case_site[cid] = site

            # keep best payload for evidence / quality boost
            if contrib > case_best_score[cid]:
                case_best_score[cid] = contrib
                case_best_payload[cid] = payload

    # -----------------------------
    # Final case score with consistency bonus + clinical quality boost
    # -----------------------------
    case_final_score = {}
    for cid, base_sum in case_total_score.items():
        support = len(case_supported_by_chunks[cid])
        bonus = 1.0 + CONSISTENCY_BONUS * max(0, support - 1)

        payload = case_best_payload.get(cid, {})
        qual = clinical_quality_boost(payload)  # re-ranking quality factor

        case_final_score[cid] = float(base_sum) * float(bonus) * float(qual)

    # -----------------------------
    # Aggregate by primary_site (pre-calibration)
    # -----------------------------
    site_scores = defaultdict(float)
    for cid, sc in case_final_score.items():
        site = case_site.get(cid)
        if site:
            site_scores[site] += float(sc)

    # -----------------------------
    # Evidence: best cases per site (build BEFORE calibration)
    # -----------------------------
    evidence_by_site = defaultdict(list)
    for cid, sc in case_final_score.items():
        site = case_site.get(cid)
        if not site:
            continue

        payload = case_best_payload.get(cid, {})
        txt = payload.get("chunk_text", "")
        snippet = (txt[:220] + "...") if isinstance(txt, str) and len(txt) > 220 else txt

        evidence_by_site[site].append({
            "case_id": str(payload.get("case_id", cid)),        # dataset case id
            "score": float(sc),
            "section": payload.get("section"),
            "snippet": snippet,
            "chunk_id_raw": payload.get("chunk_id_raw")         # optional if you stored it
        })

    for site in evidence_by_site:
        evidence_by_site[site] = sorted(
            evidence_by_site[site],
            key=lambda d: d["score"],
            reverse=True
        )[:MAX_EVIDENCE_PER_SITE]

    # -----------------------------
    # ✅ CALIBRATION: penalize sites with weak evidence
    # (must happen AFTER evidence_by_site exists, BEFORE %)
    # -----------------------------
    site_strong_counts = {}
    for site, evidences in evidence_by_site.items():
        site_strong_counts[site] = sum(
            1 for e in evidences
            if is_strong_section(e.get("section"))
        )

    for site in list(site_scores.keys()):
        if site_strong_counts.get(site, 0) < 2:
            site_scores[site] *= 0.75

    # -----------------------------
    # Normalize -> %
    # -----------------------------
    total = sum(site_scores.values())
    pct = {s: (v / total) * 100.0 for s, v in site_scores.items()} if total > 0 else {}
    sorted_sites = sorted(pct.items(), key=lambda x: x[1], reverse=True)

    debug = {
        "sorted_sites": sorted_sites,
        "site_scores": dict(site_scores),
        "n_input_chunks": N,
        "case_supported_by_chunks": {k: len(v) for k, v in case_supported_by_chunks.items()},
        "evidence": dict(evidence_by_site),
        "site_strong_counts": site_strong_counts,
        "params": {
            "K_DENSE": K_DENSE,
            "K_SPARSE": K_SPARSE,
            "K_FUSED": K_FUSED,
            "RRF_K": RRF_K,
            "MAX_CASES_PER_INPUT_CHUNK": MAX_CASES_PER_INPUT_CHUNK,
            "CONSISTENCY_BONUS": CONSISTENCY_BONUS,
            "CALIBRATION_STRONG_MIN": 2,
            "CALIBRATION_PENALTY": 0.75,
        }
    }
    return pct, debug


# =========================
# CLI
# =========================
if __name__ == "__main__":
    info = client.get_collection(COLLECTION)
    print(f"Collection status: {info.status} points: {info.points_count}")

    pct, dbg = predict_primary_site()

    print("\n==============================")
    print(" Predicted primary_site (%)")
    print("==============================")
    for site, p in dbg["sorted_sites"][:10]:
        print(f"{site:15s} {p:6.2f}%")

    print("\n==============================")
    print("Evidence (top sites)")
    print("==============================")
    for site, p in dbg["sorted_sites"][:3]:
        print(f"\n--- {site} ({p:.2f}%) ---")
        for e in dbg["evidence"].get(site, [])[:MAX_EVIDENCE_PER_SITE]:
            print(f"  score={e['score']:.4f} case={e['case_id']} sec={e['section']} | {e['snippet']}")