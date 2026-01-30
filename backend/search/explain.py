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

from backend.search.search import predict_primary_site


# -------------------------
# Helpers
# -------------------------
def _truncate(text: str, n: int = 260) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def _pct_lookup(percentages: dict, site: str) -> float:
    # percentages may be dict {site: pct} or list; keep robust
    if isinstance(percentages, dict):
        return float(percentages.get(site, 0.0))
    return 0.0


def build_context_from_evidence(
    evidence_by_site: dict,
    top_sites: list,
    max_items_per_site: int = 6,
    max_chars: int = 6000
) -> str:
    """
    Context sent to LLM: includes scores (OK) to help ranking,
    but we will NOT display scores to the user.
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
        "- Keep it clinician-friendly and concise.\n"
    )

    user = (
        f"Question:\n{question}\n\n"
        f"Context:\n{context}\n\n"
        "Return a structured explanation with:\n"
        "A) Why top-1 is leading (2-4 lines)\n"
        "B) What would help separate top-1 vs top-2 (bullets)\n"
        "C) What would help separate top-1 vs top-3 (bullets)\n"
        "D) Generic phrases to treat as weak evidence (bullets)\n"
        "E) Uncertainty note (1-2 lines)\n"
        "Use citations like (BIOCUP_00001, IHC).\n"
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


def format_console_report(
    collection_name: str,
    points_count: int | None,
    sorted_sites: list,
    evidence_by_site: dict,
    llm_explanation: str,
    top_n: int = 7,
    evidence_items_per_top_site: int = 3
) -> str:
    """
    User-friendly console output:
    - shows percentages only (no scores)
    - shows a few evidence snippets with citations
    """
    lines = []
    lines.append("════════════════════════════════════════════════════")
    lines.append("BioCUP • Search Summary")
    lines.append("════════════════════════════════════════════════════")
    lines.append(f"Collection: {collection_name}")
    if points_count is not None:
        lines.append(f"Indexed cases/chunks (points): {points_count}")
    lines.append("")

    # Top predictions
    lines.append("Top predicted primary sites")
    lines.append("--------------------------------------------")
    for site, pct in sorted_sites[:top_n]:
        lines.append(f"- {site:<10}  {float(pct):>6.2f}%")
    lines.append("")

    # Explanation
    lines.append("LLM explanation (evidence-based)")
    lines.append("--------------------------------------------")
    lines.append(llm_explanation.strip() if llm_explanation else "No explanation available.")
    lines.append("")

    # Evidence snippets (no score)
    top_sites = [s for s, _ in sorted_sites[:3]]
    lines.append("Evidence examples (no scores shown)")
    lines.append("--------------------------------------------")
    for site in top_sites:
        lines.append(f"\n• {site.upper()}")
        ev = evidence_by_site.get(site, [])[:evidence_items_per_top_site]
        if not ev:
            lines.append("  - (No evidence snippets available)")
            continue
        for e in ev:
            case_id = e.get("case_id")
            sec = e.get("section")
            snippet = _truncate(e.get("snippet") or "", 260)
            lines.append(f"  - ({case_id}, {sec}) {snippet}")

    lines.append("\nNote: This tool supports retrieval review only and does not provide medical advice.")
    return "\n".join(lines)


def format_markdown_report(
    collection_name: str,
    points_count: int | None,
    sorted_sites: list,
    evidence_by_site: dict,
    llm_explanation: str,
    top_n: int = 7,
    evidence_items_per_top_site: int = 3
) -> str:
    top_sites = [s for s, _ in sorted_sites[:3]]

    md = []
    md.append("# BioCUP — Search Summary\n")
    md.append(f"**Collection:** `{collection_name}`  \n")
    if points_count is not None:
        md.append(f"**Points:** `{points_count}`  \n")

    md.append("\n## Top predicted primary sites\n")
    md.append("| Site | Probability |\n|---|---:|\n")
    for site, pct in sorted_sites[:top_n]:
        md.append(f"| {site} | {float(pct):.2f}% |\n")

    md.append("\n## LLM explanation (evidence-based)\n")
    md.append("> This explanation is generated using retrieved evidence only.\n\n")
    md.append(llm_explanation.strip() if llm_explanation else "_No explanation available._")
    md.append("\n\n## Evidence examples (no scores shown)\n")

    for site in top_sites:
        md.append(f"\n### {site}\n")
        ev = evidence_by_site.get(site, [])[:evidence_items_per_top_site]
        if not ev:
            md.append("- _No evidence snippets available._\n")
            continue
        for e in ev:
            case_id = e.get("case_id")
            sec = e.get("section")
            snippet = _truncate(e.get("snippet") or "", 320)
            md.append(f"- **({case_id}, {sec})** {snippet}\n")

    md.append("\n---\n")
    md.append("_Note: This tool supports retrieval review only and does not provide medical advice._\n")
    return "".join(md)


def run_explain() -> dict:
    points_count = None
    if os.getenv("BIOCUP_DEBUG") == "1":
        info = qdrant.get_collection(COLLECTION)
        points_count = getattr(info, "points_count", None)
        print(f"Collection status: {info.status} points: {points_count}")

    pct, dbg = predict_primary_site()

    sorted_sites = dbg.get("sorted_sites", [])  # list[(site, pct)]
    top_sites = [s for s, _ in sorted_sites[:3]]

    context = build_context_from_evidence(
        dbg.get("evidence", {}),
        top_sites=top_sites
    )

    question = (
        "Explain why the top predicted primary site is most supported compared to the next two sites. "
        "Highlight discriminative markers/phrases if present and flag generic phrases that are not organ-specific."
    )

    try:
        answer = explain_with_llm(question, context)
    except Exception as e:
        answer = f"LLM explanation unavailable: {e}"

    # Clean evidence: remove scores before output
    clean_evidence = {}
    for site, items in (dbg.get("evidence", {}) or {}).items():
        clean_evidence[site] = []
        for e in items:
            clean_evidence[site].append({
                "case_id": e.get("case_id"),
                "section": e.get("section"),
                "snippet": e.get("snippet"),
            })

    clean = {
        "collection_name": COLLECTION,
        "points_count": points_count,
        "top_sites": top_sites,
        "sorted_sites": sorted_sites[:10],   # (site, percentage)
        "llm_explanation": answer,
        "evidence": clean_evidence,
    }

    # Save clean JSON
    out_json = ROOT / "backend" / "search" / "explain_output_clean.json"
    out_json.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save markdown report
    report_md = ROOT / "backend" / "search" / "explain_report.md"
    report_md.write_text(
        format_markdown_report(
            collection_name=COLLECTION,
            points_count=points_count,
            sorted_sites=sorted_sites,
            evidence_by_site=clean_evidence,
            llm_explanation=answer,
            top_n=7,
            evidence_items_per_top_site=3
        ),
        encoding="utf-8"
    )

    # Print pretty console report
    console = format_console_report(
        collection_name=COLLECTION,
        points_count=points_count,
        sorted_sites=sorted_sites,
        evidence_by_site=clean_evidence,
        llm_explanation=answer,
        top_n=7,
        evidence_items_per_top_site=3
    )
    print(console)
    print(f"\nSaved:\n- {out_json}\n- {report_md}")

    return clean


if __name__ == "__main__":
    run_explain()
