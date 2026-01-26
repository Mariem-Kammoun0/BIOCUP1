# backend/search/explain.py
# ============================================================
# BioCUP — LLM Explanation for predicted primary_site
# - Runs predict_primary_site() from search_final.py (or search.py)
# - Builds a compact context from evidence snippets
# - Calls OpenAI to explain why top-1 beats top-2/top-3
# ============================================================

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from qdrant_client import QdrantClient


# -------------------------
# Make imports work (fix ModuleNotFoundError: backend)
# -------------------------
ROOT = Path(__file__).resolve().parents[2]  # BIOCUP1
sys.path.append(str(ROOT))

# Load .env from project root (more reliable than load_dotenv() alone)
load_dotenv(dotenv_path=ROOT / ".env", override=True)

COLLECTION = "biocup_hybrid_splade_v1"

client = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ.get("QDRANT_API_KEY")
)

# ✅ Import from your FINAL search file
# If your file is named search_final.py:
from search import predict_primary_site
 # <- use this
# If you still use search.py, replace the line above with:
# from backend.search.search import predict_primary_site


def build_context_from_evidence(
    evidence_by_site: dict,
    top_sites: list,
    max_items_per_site: int = 6,
    max_chars: int = 6000
) -> str:
    """
    Build LLM context from Qdrant evidence snippets.
    """
    blocks = []
    total = 0

    for site in top_sites:
        blocks.append(f"\n### SITE: {site}\n")
        for e in evidence_by_site.get(site, [])[:max_items_per_site]:
            case_id = e.get("case_id")
            sec = e.get("section")
            score = e.get("score")
            snippet = e.get("snippet") or ""

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


def explain_with_llm(question: str, context: str) -> str:
    """
    Calls OpenAI. Uses ONLY provided context.
    """
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in .env (project root)")

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
        model="gpt-4o-mini",
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content


if __name__ == "__main__":
    # Optional sanity check
    info = client.get_collection(COLLECTION)
    print(f"Collection status: {info.status} points: {info.points_count}")

    pct, dbg = predict_primary_site()

    top_sites = [s for s, _ in dbg["sorted_sites"][:3]]
    context = build_context_from_evidence(dbg["evidence"], top_sites=top_sites, max_items_per_site=6)

    question = (
        "Explain why the top predicted primary site is most supported, compared to the next two sites. "
        "Highlight discriminative markers/phrases if present and flag generic phrases that are not organ-specific."
    )

    answer = explain_with_llm(question, context)

    print("\n==============================")
    print("🧠 LLM Explanation (evidence-based)")
    print("==============================\n")
    print(answer)
