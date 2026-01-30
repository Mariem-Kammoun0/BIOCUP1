# backend/search/diagnostic_refine.py
# ============================================================
# BioCUP — Iterative Diagnostic Refinement using Vector Search
# ============================================================

import os
import sys
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
from qdrant_client import QdrantClient

# -------------------------
# Path + env bootstrap FIRST
# -------------------------
ROOT = Path(__file__).resolve().parents[2]  # BIOCUP1 repo root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pathlib import Path
load_dotenv(dotenv_path=Path(".") / ".env", override=True)


COLLECTION = os.getenv("COLLECTION_NAME", "biocup_hybrid_splade_v1")

qdrant = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ.get("QDRANT_API_KEY"),
)

# -------------------------
# Internal imports (after sys.path setup)
# -------------------------
from backend.search.search_final import predict_primary_site
from backend.embedding.rebuild_input_embeddings import rebuild_embeddings_from_sections
from backend.search.qdrant_upsert_validated import upsert_validated_input_case


# -------------------------
# Build a structured report like your dataset
# -------------------------
def build_patient_sections(
    patient_summary: str,
    doctor_updates: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Returns a list of sections in the same spirit as your dataset (IHC, DIAGNOSIS, etc.)
    Keeps it generic and clinician-facing.
    """
    updates = doctor_updates or {}

    def _get(key: str) -> str:
        v = updates.get(key)
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return ", ".join(map(str, v))
        return str(v)

    sections: List[Dict[str, Any]] = []

    # GENERAL / CLINICAL
    sections.append({
        "section": "GENERAL",
        "chunk_index": 0,
        "chunk_text": patient_summary.strip(),
        "has_ihc": False,
        "has_lymph": False,
        "has_margins": False,
        "has_tnm": False,
        "has_size": False,
        "is_admin_noise": 0,
    })

    # DIAGNOSIS-like
    diag = _get("DIAGNOSIS") or _get("diagnosis") or ""
    if diag.strip():
        sections.append({
            "section": "DIAGNOSIS",
            "chunk_index": len(sections),
            "chunk_text": f"Diagnosis / pathology impression:\n{diag.strip()}",
            "is_admin_noise": 0,
        })

    # IHC
    ihc = _get("IHC") or _get("ihc") or ""
    if ihc.strip():
        sections.append({
            "section": "IHC",
            "chunk_index": len(sections),
            "chunk_text": f"IHC results:\n{ihc.strip()}",
            "is_admin_noise": 0,
        })

    # IMAGING
    imaging = _get("IMAGING") or _get("imaging") or _get("Imaging") or ""
    if imaging.strip():
        sections.append({
            "section": "GENERAL",
            "chunk_index": len(sections),
            "chunk_text": f"Imaging findings:\n{imaging.strip()}",
            "is_admin_noise": 0,
        })

    # LABS / TUMOR MARKERS
    labs = _get("LABS") or _get("tumor_markers") or _get("TumorMarkers") or ""
    if labs.strip():
        sections.append({
            "section": "GENERAL",
            "chunk_index": len(sections),
            "chunk_text": f"Laboratory / tumor markers:\n{labs.strip()}",
            "is_admin_noise": 0,
        })

    # Extra updates as a compact note
    other_lines = []
    for k, v in updates.items():
        if k.upper() in {"DIAGNOSIS", "IHC", "IMAGING", "LABS", "TUMORMARKERS"}:
            continue
        if v is None or v == "" or v == []:
            continue
        other_lines.append(f"- {k}: {v}")
    if other_lines:
        sections.append({
            "section": "COMMENT",
            "chunk_index": len(sections),
            "chunk_text": "Doctor-provided updates:\n" + "\n".join(other_lines),
            "is_admin_noise": 0,
        })

    return sections


# -------------------------
# Evidence/context for LLM
# -------------------------
def build_context_from_evidence(
    evidence_by_site: dict,
    top_sites: list,
    max_items_per_site: int = 6,
    max_chars: int = 6000,
) -> str:
    blocks = []
    total = 0

    for site in top_sites:
        blocks.append(f"\n### SITE: {site}\n")
        for e in evidence_by_site.get(site, [])[:max_items_per_site]:
            case_id = e.get("case_id")
            sec = e.get("section")
            score = e.get("score")
            snippet = (e.get("snippet") or "").strip()

            block = (
                f"(case_id={case_id}, section={sec}, score={float(score):.4f})\n"
                f"{snippet}\n"
            )
            blocks.append(block)
            total += len(block)
            if total >= max_chars:
                break
        if total >= max_chars:
            break

    return "\n".join(blocks)


def summarize_uncertainty(dbg: Dict[str, Any], top_k: int = 3) -> Dict[str, Any]:
    sorted_sites = dbg.get("sorted_sites", [])[:top_k]
    sites = [s for s, _ in sorted_sites]
    scores = {s: float(sc) for s, sc in sorted_sites}

    margin_12 = None
    if len(sorted_sites) >= 2:
        margin_12 = float(sorted_sites[0][1]) - float(sorted_sites[1][1])

    reasons = []
    if margin_12 is not None and margin_12 < 5.0:
        reasons.append("Top-1 vs Top-2 margin is small (close match).")
    if len(sites) >= 3:
        reasons.append("Multiple sites appear plausible based on retrieved evidence.")
    if not dbg.get("evidence"):
        reasons.append("No evidence snippets were returned (missing payload/snippets).")

    return {
        "top_sites": sites,
        "scores": scores,
        "score_margin_top1_top2": margin_12,
        "uncertainty_reasons": reasons,
    }


# -------------------------
# OpenAI calls
# -------------------------
def _openai_client():
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in .env (project root)")
    return OpenAI(api_key=api_key)


def explain_top_site_with_llm(question: str, dbg: Dict[str, Any], top_k: int = 3) -> str:
    client_oa = _openai_client()

    sorted_sites = dbg.get("sorted_sites", [])[:top_k]
    top_sites = [s for s, _ in sorted_sites]

    evidence = dbg.get("evidence", {})
    site_stats = {}
    pct_map = dict(sorted_sites)

    for s in top_sites:
        ev = evidence.get(s, []) or []
        best = max([float(e.get("score", 0.0)) for e in ev], default=0.0)
        site_stats[s] = {
            "pct": float(pct_map.get(s, 0.0)),
            "evidence_count": len(ev),
            "best_evidence_score": best,
            "sections_present": sorted({str(e.get("section")) for e in ev if e.get("section")}),
        }

    margin_12 = None
    if len(sorted_sites) >= 2:
        margin_12 = float(sorted_sites[0][1]) - float(sorted_sites[1][1])

    context = build_context_from_evidence(
        evidence_by_site=evidence,
        top_sites=top_sites,
        max_items_per_site=6,
        max_chars=6000,
    )

    system = (
        "You are a clinical retrieval assistant for BioCUP.\n"
        "Rules:\n"
        "- Use ONLY the provided context and numeric site_stats.\n"
        "- Do NOT invent facts.\n"
        "- Only mention sections that appear in the evidence context.\n"
        "- Provide citations as (case_id, section) for every evidence bullet.\n"
        "- If >=3 evidence items exist for top-1, cite at least 3.\n"
        "- If margin_top1_top2 < 5%, explicitly state uncertainty is high.\n"
        "- Do NOT give medical advice.\n"
    )

    user_payload = {
        "question": question,
        "margin_top1_top2_pct": margin_12,
        "site_stats": site_stats,
        "context": context,
        "required_format": [
            "1) Top-site reasoning (short, must align with site_stats)",
            "2) Top-1 vs Top-2 evidence bullets (each bullet must end with (case_id, section))",
            "3) Top-1 vs Top-3 evidence bullets (each bullet must end with (case_id, section))",
            "4) Generic/weak evidence to ignore (bullets)",
            "5) Conclusion + explicit uncertainty note (use margin)",
        ],
    }

    resp = client_oa.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    )
    return resp.choices[0].message.content


def propose_tests_with_llm(
    patient_summary: str,
    dbg: Dict[str, Any],
    max_sites: int = 3,
) -> Dict[str, Any]:
    uncertainty = summarize_uncertainty(dbg, top_k=max_sites)
    top_sites = uncertainty["top_sites"]

    context = build_context_from_evidence(
        dbg.get("evidence", {}),
        top_sites=top_sites,
        max_items_per_site=6,
        max_chars=6000,
    )

    system = (
        "You are a clinician-facing decision-support assistant for Cancer of Unknown Primary (CUP).\n"
        "You are NOT diagnosing.\n"
        "Your role: suggest additional information/tests that could reduce uncertainty in retrieval.\n"
        "Rules:\n"
        "- Be conservative and generic.\n"
        "- Use ONLY the provided patient summary + evidence context + uncertainty reasons.\n"
        "- If evidence is insufficient, request what is missing.\n"
        "- Do not give medical advice or treatment.\n"
        "- Output JSON only, no markdown.\n"
    )

    payload = {
        "patient_summary": patient_summary,
        "top_retrieved_sites": top_sites,
        "uncertainty": uncertainty,
        "evidence_context": context,
        "output_schema": {
            "questions_to_clarify": [
                {"field": "...", "question": "...", "type": "text|single_select|multi_select", "options": []}
            ],
            "recommended_investigations": [
                {
                    "category": "Imaging|IHC|PathologyDetail|ClinicalPattern|Lab",
                    "item": "...",
                    "rationale": "...",
                    "expected_answer_type": "text|boolean|single_select",
                    "options": [],
                }
            ],
            "rerank_strategy": {"how_to_use_new_info": ["...short bullets..."]},
        },
    }

    client_oa = _openai_client()
    resp = client_oa.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )

    raw = resp.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "questions_to_clarify": [],
            "recommended_investigations": [],
            "rerank_strategy": {"how_to_use_new_info": ["LLM returned non-JSON; check raw_text."]},
            "raw_text": raw,
        }


# -------------------------
# Core iterative loop
# -------------------------
def run_iterative_refinement(
    patient_summary: str,
    doctor_updates: Optional[Dict[str, Any]] = None,
    validated: bool = False,
    validated_case_id: Optional[str] = None,
    validated_primary_site: Optional[str] = None,
) -> Dict[str, Any]:
    """
    1) Build sections
    2) rebuild embeddings files (meta.parquet/dense.npy/sparse_splade.npz)
    3) predict_primary_site() reads embeddings files and queries Qdrant
    4) LLM explanation + test recommendations
    5) if doctor_updates provided -> enrich -> rebuild -> rerun
    6) if validated -> upsert the final input case into Qdrant
    """

    # ---------- Initial run
    sections1 = build_patient_sections(patient_summary, doctor_updates=None)
    rebuild_embeddings_from_sections(sections1, patient_id="P_INPUT")

    pct1, dbg1 = predict_primary_site()
    top_sites_1 = [s for s, _ in dbg1.get("sorted_sites", [])[:3]]
    pred1 = top_sites_1[0] if top_sites_1 else None

    explanation1 = explain_top_site_with_llm(
        question="Explain why the top predicted primary site is most supported compared to the next two sites.",
        dbg=dbg1,
    )

    tests_plan = propose_tests_with_llm(patient_summary, dbg1, max_sites=3)

    result: Dict[str, Any] = {
        "initial": {
            "predicted_primary_site": pred1,
            "top_sites": top_sites_1,
            "pct": pct1,
            "explanation": explanation1,
            "uncertainty": summarize_uncertainty(dbg1, top_k=3),
            "evidence": dbg1.get("evidence", {}),
        },
        "diagnostic_refinement": tests_plan,
        "refined": None,
        "final_case_upsert": None,
    }

    # ---------- Refined run
    pred_final = pred1

    if doctor_updates:
        sections2 = build_patient_sections(patient_summary, doctor_updates=doctor_updates)
        rebuild_embeddings_from_sections(sections2, patient_id="P_INPUT")

        pct2, dbg2 = predict_primary_site()
        top_sites_2 = [s for s, _ in dbg2.get("sorted_sites", [])[:3]]
        pred2 = top_sites_2[0] if top_sites_2 else None

        explanation2 = explain_top_site_with_llm(
            question="Re-explain after updates: why the top predicted primary site is most supported vs the next two.",
            dbg=dbg2,
        )

        result["refined"] = {
            "doctor_updates": doctor_updates,
            "predicted_primary_site": pred2,
            "top_sites": top_sites_2,
            "pct": pct2,
            "explanation": explanation2,
            "uncertainty": summarize_uncertainty(dbg2, top_k=3),
            "evidence": dbg2.get("evidence", {}),
        }

        pred_final = pred2

    # ---------- Validation upsert
    if validated:
        case_id = validated_case_id or f"BIOCUP_INPUT_VALIDATED_{uuid.uuid4().hex[:10]}"
        chosen_primary = validated_primary_site or pred_final or "unknown"

        embeddings_dir = ROOT / "data" / "input" / "embeddings"
        chunks_csv = ROOT / "data" / "input" / "chunks" / "input_chunks.csv"

        up = upsert_validated_input_case(
            collection_name=COLLECTION,
            patient_case_id=case_id,
            predicted_primary_site=chosen_primary,
            embeddings_dir=embeddings_dir,
            chunks_csv=chunks_csv,
        )
        result["final_case_upsert"] = up

    return result


# -------------------------
# CLI
# -------------------------
if __name__ == "__main__":
    print("QDRANT_URL:", os.environ.get("QDRANT_URL"))
    print("COLLECTION_NAME:", COLLECTION)

    if not qdrant.collection_exists(COLLECTION):
        cols = qdrant.get_collections().collections
        print("\n❌ Collection not found:", COLLECTION)
        print("✅ Available collections:")
        for c in cols:
            print(" -", c.name)
        raise SystemExit(1)

    info = qdrant.get_collection(COLLECTION)
    print(f"\n✅ Collection status: {info.status} points: {info.points_count}\n")

    patient_summary = "CUP case summary: metastasis noted; primary uncertain."

    doctor_updates = {
        "IHC": "TTF-1 positive; CK7 positive; CK20 negative",
        "IMAGING": "CT chest shows suspicious right upper lobe lesion",
        "TumorMarkers": "CEA normal; CA19-9 mildly elevated",
    }

    out = run_iterative_refinement(
        patient_summary=patient_summary,
        doctor_updates=doctor_updates,
        validated=False,
        validated_case_id=None,
        validated_primary_site=None,
    )

    print(json.dumps(out, indent=2, ensure_ascii=False))
