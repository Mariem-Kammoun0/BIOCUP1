# backend/search/explain.py
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# -------------------------
# Path + env
# -------------------------
ROOT = Path(__file__).resolve().parents[2]  # BIOCUP1
sys.path.append(str(ROOT))

load_dotenv(dotenv_path=ROOT / ".env", override=True)

COLLECTION = os.getenv("COLLECTION_NAME", "biocup_hybrid_splade_v1")

qdrant = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ.get("QDRANT_API_KEY")
)

# If your file is backend/search/search_final.py:
from backend.search.search import predict_primary_site


def build_context_from_evidence(
    evidence_by_site: dict,
    top_sites: list,
    max_items_per_site: int = 6,
    max_chars: int = 6000
) -> str:
    blocks = []
    total = 0

    for site in top_sites:
        blocks.append(f"\n### SITE: {site}\n")
        for e in evidence_by_site.get(site, [])[:max_items_per_site]:
            case_id = e.get("case_id")
            sec = e.get("section")
            score = e.get("score")
            snippet = e.get("snippet") or ""

            score_val = float(score) if score is not None else 0.0

            block = (
                f"(case_id={case_id}, section={sec}, score={score_val:.4f})\n"
                f"{snippet}\n"
            )
            blocks.append(block)
            total += len(block)
            if total >= max_chars:
                break
        if total >= max_chars:
            break

    return "\n".join(blocks)


def explain_with_llm(question: str, context: str) -> str:
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in BIOCUP1/.env")

    client_oa = OpenAI(api_key=api_key)

    system = (
        "You are a clinical retrieval assistant for BioCUP.\n"
        "Rules:\n"
        "- Use ONLY the provided context.\n"
        "- Do NOT invent facts.\n"
        "- If context is insufficient, say what is missing.\n"
        "- Provide citations as (case_id, section).\n"
        "- Do NOT give medical advice. Summarize evidence patterns only.\n"
    )

    user = (
        f"Question:\n{question}\n\n"
        f"Context:\n{context}\n\n"
        "Answer format:\n"
        "1) Top-site reasoning (short)\n"
        "2) Evidence that supports top-1 vs top-2 (bullets)\n"
        "3) Evidence that supports top-1 vs top-3 (bullets)\n"
        "4) Generic/weak evidence to ignore (bullets)\n"
        "5) Conclusion with uncertainty note\n"
    )

    resp = client_oa.chat.completions.create(
        model=os.getenv("BIOCUP_OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content


def run_explain() -> dict:
    if os.getenv("BIOCUP_DEBUG") == "1":
        info = qdrant.get_collection(COLLECTION)
        print(f"Collection status: {info.status} points: {info.points_count}")

    pct, dbg = predict_primary_site()

    top_sites = [s for s, _ in dbg["sorted_sites"][:3]]
    context = build_context_from_evidence(dbg.get("evidence", {}), top_sites=top_sites)

    question = (
        "Explain why the top predicted primary site is most supported, compared to the next two sites. "
        "Highlight discriminative markers/phrases if present and flag generic phrases that are not organ-specific."
    )

    # Option: do not crash pipeline if OpenAI is missing
    try:
        answer = explain_with_llm(question, context)
    except Exception as e:
        answer = f"LLM explanation unavailable: {e}"

    out = {
        "sorted_sites": dbg.get("sorted_sites", [])[:10],
        "top_sites": top_sites,
        "percentages": pct,
        "evidence": dbg.get("evidence", {}),
        "llm_explanation": answer,
        "collection_name": COLLECTION,
    }

    # ✅ FIXED OUTPUT PATH (no env vars)
    out_path = ROOT / "backend" / "search" / "explain_output.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f" explain_output saved to: {out_path}")
    return out


if __name__ == "__main__":
    result = run_explain()
    print(json.dumps(result, ensure_ascii=False, indent=2))
