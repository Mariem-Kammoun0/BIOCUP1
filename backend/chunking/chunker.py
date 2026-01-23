# ============================================================
# BioCUP — Clinically reliable semantic chunking (1 row = 1 case)
# - Fewer, robust sections + clinical routing
# - No mixed chunks (TNM/IHC/Margins/Lymph routed)
# - Less repetition (exact + near-duplicate within same case)
# - Safer splitting (no mid-word starts)
# ============================================================

import re
import json
import hashlib
import pandas as pd
from typing import Dict, List, Any, Tuple

from chonkie import SemanticChunker
from chonkie.embeddings.sentence_transformer import SentenceTransformerEmbeddings

# =========================
# CONFIG
# =========================
INPUT_CSV = "biocup_subset.csv"
OUTPUT_CSV = "biocup_chunks.csv"
OUTPUT_STATS_JSON = "biocup_chunks_stats.json"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

MAX_CHUNK_SIZE = 520
MIN_CHUNK_SIZE = 140
SIMILARITY_THRESHOLD = 0.70

MIN_CHARS_PER_CHUNK = 120
MAX_CHARS_PER_CHUNK = 2200

DROP_DUPLICATE_CHUNKS = True
DROP_NEAR_DUPLICATES = True
NEAR_DUP_SIM_THRESHOLD = 0.92  # token Jaccard overlap

REQUIRED_COLS = ["case_id", "primary_site", "tcga_type", "patient_id", "report_text"]


# =========================
# HEADINGS (keep small)
# =========================
RAW_HEADERS = [
    "FINAL DIAGNOSIS","DIAGNOSIS",
    "INTERPRETATION AND DIAGNOSIS","CLINICAL HISTORY","CLINICAL NOTES",
    "HISTORY","SPECIMEN","SPECIMENS SUBMITTED",
    "SPECIMENS RECEIVED","PROCEDURE","OPERATION",
    "GROSS DESCRIPTION","GROSS",
    "MICROSCOPIC DESCRIPTION","MICROSCOPIC",
    "MICRO","SYNOPTIC REPORT","SYNOPTIC",
    "CAP SYNOPTIC","IMMUNOHISTOCHEMISTRY",
    "IMMUNOHISTOCHEMICAL","IHC","COMMENT","COMMENTS",
    "NOTE","NOTES",
    "INTRA OPERATIVE CONSULTATION",
    "INTRAOPERATIVE CONSULTATION",
    "FROZEN SECTION","SPECIAL STAINS",
]

HEADER_BUCKET = {
    "FINAL DIAGNOSIS": "DIAGNOSIS",
    "DIAGNOSIS": "DIAGNOSIS",
    "INTERPRETATION AND DIAGNOSIS": "DIAGNOSIS",

    "CLINICAL HISTORY": "CLINICAL_HISTORY",
    "CLINICAL NOTES": "CLINICAL_HISTORY",
    "HISTORY": "CLINICAL_HISTORY",

    "SPECIMEN": "SPECIMEN",
    "SPECIMENS RECEIVED": "SPECIMEN",
    "SPECIMENS SUBMITTED": "SPECIMEN",
    "PROCEDURE": "SPECIMEN",
    "OPERATION": "SPECIMEN",

    "GROSS": "GROSS",
    "GROSS DESCRIPTION": "GROSS",

    "MICRO": "MICRO",
    "MICROSCOPIC": "MICRO",
    "MICROSCOPIC DESCRIPTION": "MICRO",

    "SYNOPTIC": "SYNOPTIC",
    "SYNOPTIC REPORT": "SYNOPTIC",
    "CAP SYNOPTIC": "SYNOPTIC",

    "IHC": "IHC",
    "IMMUNOHISTOCHEMISTRY": "IHC",
    "IMMUNOHISTOCHEMICAL": "IHC",

    "COMMENT": "COMMENT",
    "COMMENTS": "COMMENT",
    "NOTE": "COMMENT",
    "NOTES": "COMMENT",

    "INTRA OPERATIVE CONSULTATION": "COMMENT",
    "INTRAOPERATIVE CONSULTATION": "COMMENT",
    "FROZEN SECTION": "COMMENT",
    "SPECIAL STAINS": "COMMENT",
}

def normalize_heading(h: str) -> str:
    h = (h or "").strip().upper()
    return HEADER_BUCKET.get(h, "GENERAL")


# =========================
# CLEANING (safe + targeted)
# =========================
_PAGE_RE = re.compile(r"(?i)\bpage\s*:?\s*\d+\s*(of\s*\d+)?\b")
_STATUS_RE = re.compile(r"(?i)\bstatus\s*:\s*corrected\b.*?(?=(\.\s)|$)")
_RULE_RE = re.compile(r"(=|-|_){3,}")
_WS_RE = re.compile(r"[ \t]+")

# Remove frequent admin boilerplate lines without removing clinical content
DROP_LINE_HINTS = re.compile(
    r"(?i)\b("
    r"print date/time|distributed to|patient locations|verified:|electronic signature|"
    r"this report was electronically signed|slides? received at|reported\s+\d+\.\d+|"
    r"other surgical pathology specimens|tissue code|source of specimen|"
    r"specimen was placed in formalin|ischemic time|time specimen was removed|"
    r"specimen is in formalin more than|submitted for future studies|tumor bank|"
    r"summary of sections|block\.?\s+sect\.?\s+site|pcs\.?|continued on next page|"
    r"matrix|format|containers|amount/per|specification"
    r")\b"
)

# Cassette labels like 8A-8H, A1, B2 etc (often noise for similarity)
_CASSETTE_RE = re.compile(r"\b\d+[A-Z](?:-\d+[A-Z])?\b|\b[A-Z]\d\b")

def clean_text_keep_lines(text: Any) -> str:
    """Clean while preserving line structure for header detection."""
    if not isinstance(text, str):
        return ""
    t = text.replace("\x0c", "\n").replace("\r", "\n")
    t = _RULE_RE.sub("\n", t)

    lines = []
    for ln in t.splitlines():
        ln = _PAGE_RE.sub(" ", ln)
        ln = _STATUS_RE.sub(" ", ln)
        ln = _CASSETTE_RE.sub(" ", ln)
        ln = _WS_RE.sub(" ", ln).strip()
        # Drop purely admin-ish lines
        if ln and DROP_LINE_HINTS.search(ln) and len(ln) < 180:
            continue
        lines.append(ln)

    t2 = "\n".join(lines)
    t2 = re.sub(r"\n{3,}", "\n\n", t2).strip()
    return t2

def clean_text_flat(text: str) -> str:
    """Flatten after section detection."""
    if not text:
        return ""
    t = text.replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\.\s*\.", ".", t)
    return t


# =========================
# SECTION SPLITTING (more robust)
# =========================
HEAD_RE = re.compile(
    r"(?im)^(?P<h>(" + "|".join(map(re.escape, RAW_HEADERS)) + r"))\s*[:\-]?\s*(?P<rest>.*)$"
)

INLINE_DIAG_RE = re.compile(r"(?i)\bDIAGNOSIS\b\s*[:.]")

def split_by_sections(report_text: str) -> List[Dict[str, str]]:
    t = clean_text_keep_lines(report_text)
    if not t:
        return []

    # 🔑 INLINE DIAGNOSIS FIX
    if INLINE_DIAG_RE.search(t):
        pre, post = re.split(INLINE_DIAG_RE, t, maxsplit=1)
        sections = []
        if pre.strip():
            sections.append({
                "section": "GENERAL",
                "text": clean_text_flat(pre)
            })
        if post.strip():
            sections.append({
                "section": "DIAGNOSIS",
                "text": clean_text_flat(post)
            })
        return sections

    # collect headings
    matches = list(HEAD_RE.finditer(t))
    if not matches:
        return [{"section": "GENERAL", "text": clean_text_flat(t)}]

    out: List[Dict[str, str]] = []

    for i, m in enumerate(matches):
        raw_h = m.group("h")
        bucket = normalize_heading(raw_h)

        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(t)

        body = (m.group("rest") + "\n" + t[start:end]).strip()
        body_flat = clean_text_flat(body)

        if not body_flat:
            continue

        if (
            len(body_flat) >= 120 or
            re.search(
                r"(?i)\b(?:pT|pN|ypT|ypN)\b|immuno|margin|lymph node|metast|\bcm\b|\bmm\b",
                body_flat
            )
        ):
            out.append({
                "section": bucket,
                "text": body_flat
            })

    return out if out else [{"section": "GENERAL", "text": clean_text_flat(t)}]

# =========================
# CHONKIE INIT
# =========================
def init_chunker():
    embedder = SentenceTransformerEmbeddings(EMBEDDING_MODEL)
    return SemanticChunker(
        embedding_model=embedder,
        max_chunk_size=MAX_CHUNK_SIZE,
        min_chunk_size=MIN_CHUNK_SIZE,
        similarity_threshold=SIMILARITY_THRESHOLD
    )

def chunk_to_text(c: Any) -> str:
    if isinstance(c, str):
        return c
    if hasattr(c, "text"):
        return str(getattr(c, "text"))
    return str(c)


# =========================
# FLAGS (improved)
# =========================
_IHC_RE = re.compile(
    r"\b(?:CK\d+|AE1/AE3|CK5/6|TTF-?1|p63|p40|NAPSIN(?:-?A)?|PAX8|WT1|HER2|ER\b|PR\b|ALK\b|ROS1\b|PD-?L1\b)\b",
    re.I
)

# TNM: supports pT2, pN0, ypT1, T2N0, etc.
_TNM_RE = re.compile(
    r"(?i)\b(?:p|yp)?T\s*\d+[a-c]?\b|\b(?:p|yp)?N\s*\d+[a-c]?\b|\b(?:p|yp)?M\s*\d+[a-c]?\b|\bT\d+[a-c]?\s*N\d+[a-c]?\b"
)

# Measurements: captures 4.0 cm, 18 mm, 3.0 x 3.0 x 2.0 cm, etc.
_MEASURE_RE = re.compile(
    r"(?i)\b\d+(?:\.\d+)?\s*(?:cm|mm)\b|\b\d+(?:\.\d+)?\s*x\s*\d+(?:\.\d+)?(?:\s*x\s*\d+(?:\.\d+)?)?\s*(?:cm|mm)\b"
)

# Tumor-size cues (more specific than just "cm")
_TUMOR_SIZE_CUE_RE = re.compile(
    r"(?i)\b(tumou?r\s+size|maximum\s+tumou?r\s+dimension|greatest\s+dimension|size\s+of\s+tumou?r)\b"
)

# Margins cues
_MARGIN_RE = re.compile(
    r"(?i)\bmargin(?:s)?\b|\bresection\s+margin\b|\bclosest\s+margin\b|\bdistance\s+of\b|\bdistance\s+from\b|\bstapled\s+parenchymal\b|\bbronchial\s+resection\s+margin\b"
)

# Lymph nodes + stations
_LYMPH_RE = re.compile(
    r"(?i)\blymph\s+node(?:s)?\b|\bnodal\b|\bstation\b|\bST\s*\d+\w*\b|\bsubcarinal\b|\bparatracheal\b|\binterlobar\b|\blobar\b|\bhilar\b|\bmediastin(?:al|um)\b"
)

# Gross vs Micro cues
_GROSS_CUES = re.compile(r"(?i)\b(gross|received\s+(fresh|in\s+formalin)|measuring|weighing|inked|pleural\s+surface|sectioning|submitted)\b")
_MICRO_CUES = re.compile(r"(?i)\b(microscopic|histologic|histologic\s+grade|grade\s*[:\-]|visceral\s+pleural|lymphovascular|perineural|mitos(?:is|es)|cytologic)\b")

# Admin cues (kept conservative; avoid "container" alone)
_ADMIN_CUES = re.compile(
    r"(?i)\b(electronic(?:ally)?\s+signed|distributed\s+to|print\s+date|verified:|continued\s+on\s+next\s+page|"
    r"slides?\s+received|reported\s+\d{1,2}\.\d{1,2}\s*(?:am|pm)|tissue\s+bank|ischemic\s+time)\b"
)


def compute_flags(text: str) -> Dict[str, bool]:
    t = text or ""
    has_measure = bool(_MEASURE_RE.search(t))
    has_tumor_size = bool(_TUMOR_SIZE_CUE_RE.search(t)) and has_measure

    return {
        "has_tnm": bool(_TNM_RE.search(t)),
        # keep has_size but make it "any measurement"; tumor_size_cue is a stronger signal
        "has_size": has_measure,
        "has_ihc": bool(_IHC_RE.search(t)),
        "has_lymph": bool(_LYMPH_RE.search(t)),
        "has_margins": bool(_MARGIN_RE.search(t)),
        # optional: if you want to add new columns later
        "has_tumor_size_cue": has_tumor_size,
    }


# =========================
# ROUTER (dominance scoring)
# =========================
def _count(rex: re.Pattern, t: str) -> int:
    return len(rex.findall(t or ""))

def route_section(original: str, chunk: str) -> str:
    orig = original or "GENERAL"
    t = chunk or ""
    low = t.lower()

    # conservative ADMIN: only if strong cues present
    if _ADMIN_CUES.search(t) and len(t) < 700 and not _TNM_RE.search(t):
        return "ADMIN"

    scores = {
        "IHC": _count(_IHC_RE, t) + (2 if "immunohistochem" in low else 0),
        "SYNOPTIC": _count(_TNM_RE, t) + (2 if "pathologic stage" in low else 0) + (1 if "synoptic" in low else 0),
        "MARGINS": _count(_MARGIN_RE, t),
        "LYMPH_NODES": _count(_LYMPH_RE, t),
        "GROSS": (2 if _GROSS_CUES.search(t) else 0) + (1 if "measuring" in low else 0),
        "MICRO": (2 if _MICRO_CUES.search(t) else 0) + (1 if "histologic" in low else 0),
    }

    # If original is a strong narrative section, respect it when no strong concept dominates
    preserve = orig in {"DIAGNOSIS", "COMMENT", "CLINICAL_HISTORY", "SPECIMEN"}

    # pick best
    best = max(scores.items(), key=lambda kv: kv[1])
    best_section, best_score = best

    if best_score == 0:
        return orig if preserve else "GENERAL"

    # tie-breaking priority (clinical)
    priority = ["IHC", "SYNOPTIC", "MARGINS", "LYMPH_NODES", "MICRO", "GROSS"]
    top_score = best_score
    tied = [sec for sec, sc in scores.items() if sc == top_score and sc > 0]
    if len(tied) > 1:
        for p in priority:
            if p in tied:
                best_section = p
                break

    # keep DIAGNOSIS/COMMENT if they truly dominate by structure
    if preserve and best_score <= 1:
        return orig

    return best_section


# =========================
# POST-SPLIT (concept-aware by sentence bucketing)
# =========================
_SENT_SPLIT_RE = re.compile(r"(?<=[\.\;\:])\s+")

def _concept_label(s: str) -> str:
    """Return dominant concept for a sentence."""
    if _ADMIN_CUES.search(s):
        return "ADMIN"
    if _IHC_RE.search(s) or "immunohistochem" in s.lower():
        return "IHC"
    if _TNM_RE.search(s) or "pathologic stage" in s.lower() or "synoptic" in s.lower():
        return "SYNOPTIC"
    if _MARGIN_RE.search(s):
        return "MARGINS"
    if _LYMPH_RE.search(s):
        return "LYMPH_NODES"
    if _GROSS_CUES.search(s):
        return "GROSS"
    if _MICRO_CUES.search(s):
        return "MICRO"
    return "GENERAL"

def post_split_medical(chunk_text: str) -> List[str]:
    t = (chunk_text or "").strip()
    if not t:
        return []

    # split into sentences
    sents = [s.strip() for s in _SENT_SPLIT_RE.split(t) if s.strip()]
    if len(sents) <= 1:
        return [t]

    # label each sentence
    labeled = [(s, _concept_label(s)) for s in sents]

    # If everything is same label (or mostly), keep as-is
    labels = [lab for _, lab in labeled]
    unique = set(labels)
    if len(unique) == 1:
        return [t]

    # bucket contiguous sentences of same label
    groups: List[Tuple[str, List[str]]] = []
    cur_lab = labels[0]
    cur = [labeled[0][0]]
    for s, lab in labeled[1:]:
        if lab == cur_lab:
            cur.append(s)
        else:
            groups.append((cur_lab, cur))
            cur_lab = lab
            cur = [s]
    groups.append((cur_lab, cur))

    # merge tiny fragments into neighbors (avoid mid-thought chunks)
    merged: List[str] = []
    for lab, segs in groups:
        text_seg = " ".join(segs).strip()
        if merged and (len(text_seg) < 110 or re.match(r"^[\)\,\;\:\.]", text_seg) or re.match(r"^[a-z]", text_seg)):
            merged[-1] = (merged[-1] + " " + text_seg).strip()
        else:
            merged.append(text_seg)

    # final quality filter
    merged = [x for x in merged if len(x) >= 90]
    return merged if merged else [t]



# =========================
# QUALITY + DEDUP
# =========================
def quality_ok(s: str) -> bool:
    if not s:
        return False
    s2 = s.strip()
    if len(s2) < MIN_CHARS_PER_CHUNK:
        return False
    if len(s2) > MAX_CHARS_PER_CHUNK:
        return False
    if len(set(s2)) < 12:
        return False
    return True

def normalize_for_dedup(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b\d+(\.\d+)?\b", "0", s)  # normalize numbers
    s = re.sub(r"\s+", " ", s).strip()
    return s

def token_set(s: str) -> set:
    s = re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())
    toks = [t for t in s.split() if len(t) > 2]
    return set(toks)

def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# =========================
# IDs + PREFIX
# =========================
def make_chunk_id(case_id: str, section: str, chunk_index: int, sub_index: int, chunk_text: str) -> str:
    h = hashlib.md5(chunk_text.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{case_id}|{section}|{chunk_index}|{sub_index}|{h}"

def build_context_prefix(row: pd.Series, section: str) -> str:
    return (
        f"[case_id={row.get('case_id','')} | site={row.get('primary_site','')} "
        f"| type={row.get('tcga_type','')} | section={section}] "
    )


# =========================
# MAIN PIPELINE
# =========================
def protect_numbered_lists(text: str) -> str:
    # protège les listes numérotées (1., 2., 3., etc.)
    return re.sub(r"(\n?\s*\d+\.\s+)", r" <ITEM> \1", text)


def run_pipeline() -> None:
    print("📥 Loading CSV...")
    df = pd.read_csv(INPUT_CSV)

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {list(df.columns)}")

    df = df.dropna(subset=REQUIRED_COLS).copy()
    print(f"✅ Loaded {len(df)} rows")

    print("🧠 Initializing semantic chunker...")
    chunker = init_chunker()

    all_rows: List[Dict[str, Any]] = []

    stats = {
        "cases_total": int(len(df)),
        "cases_chunked": 0,
        "sections_total": 0,
        "chunks_total_raw": 0,
        "chunks_total_after_postsplit": 0,
        "chunks_dropped_quality": 0,
        "chunks_dropped_duplicate_exact": 0,
        "chunks_dropped_duplicate_near": 0,
        "chunks_by_section": {},
    }

    print("🔪 Chunking reports...")
    for _, row in df.iterrows():
        report = row["report_text"]
        sections = split_by_sections(report)
        if not sections:
            continue

        stats["cases_chunked"] += 1

        # Per-case dedup memory
        seen_norm: set = set()
        seen_token_sets: Dict[str, List[set]] = {}

        for sec in sections:
            orig_section = sec["section"]
            sec_text = sec["text"]
            stats["sections_total"] += 1

            # 🔒 PROTECT NUMBERED LISTS BEFORE CHUNKING
            safe_text = protect_numbered_lists(sec_text)

           # 🚦 decide whether to semantic-chunk
            NO_SEMANTIC_CHUNK_SECTIONS = {"GENERAL", "SPECIMEN", "DIAGNOSIS"}

            if orig_section in NO_SEMANTIC_CHUNK_SECTIONS or len(sec_text) < 600:
                chunks = [sec_text]
            else:
                try:
                    chunks = chunker.chunk(sec_text)
                except Exception:
                    chunks = [sec_text]


            stats["chunks_total_raw"] += len(chunks)

            for chunk_index, c in enumerate(chunks):
                raw_chunk = chunk_to_text(c).replace("<ITEM>", "").strip()
                if not quality_ok(raw_chunk):
                    stats["chunks_dropped_quality"] += 1
                    continue

                # post split for mixed concepts
                concept_chunks = post_split_medical(raw_chunk)

                for sub_index, cc in enumerate(concept_chunks):
                    cc = cc.strip()
                    if not quality_ok(cc):
                        stats["chunks_dropped_quality"] += 1
                        continue

                    routed_section = route_section(orig_section, cc)

                    # exact-ish dedup
                    norm = normalize_for_dedup(cc)
                    if DROP_DUPLICATE_CHUNKS and norm in seen_norm:
                        stats["chunks_dropped_duplicate_exact"] += 1
                        continue
                    seen_norm.add(norm)

                    # near-duplicate dedup (within same case + routed section)
                    if DROP_NEAR_DUPLICATES:
                        key = routed_section
                        ts = token_set(cc)
                        prev_sets = seen_token_sets.get(key, [])
                        if len(cc) >= 320 and any(jaccard(ts, ps) >= NEAR_DUP_SIM_THRESHOLD for ps in prev_sets):
                            stats["chunks_dropped_duplicate_near"] += 1
                            continue
                        prev_sets.append(ts)
                        seen_token_sets[key] = prev_sets

                    prefix = build_context_prefix(row, routed_section)
                    chunk_text = prefix + cc

                    flags = compute_flags(cc)

                    out = {
                        "chunk_id": make_chunk_id(
                            str(row["case_id"]),
                            routed_section,
                            int(chunk_index),
                            int(sub_index),
                            cc,
                        ),
                        "case_id": row["case_id"],
                        "primary_site": row["primary_site"],
                        "tcga_type": row["tcga_type"],
                        "patient_id": row["patient_id"],
                        "section": routed_section,
                        "original_section": orig_section,
                        "chunk_index": int(chunk_index),
                        "sub_index": int(sub_index),
                        "chunk_text": chunk_text,
                        **flags,
                        "is_admin_noise": True if routed_section == "ADMIN" else False,
                    }

                    all_rows.append(out)
                    stats["chunks_total_after_postsplit"] += 1
                    stats["chunks_by_section"][routed_section] = (
                        stats["chunks_by_section"].get(routed_section, 0) + 1
                    )

    chunks_df = pd.DataFrame(all_rows)
    if chunks_df.empty:
        raise ValueError("No chunks produced. Check input and regex rules.")

    print(f"💾 Saving {len(chunks_df)} chunks -> {OUTPUT_CSV}")
    chunks_df.to_csv(OUTPUT_CSV, index=False)

    print(f"📊 Saving stats -> {OUTPUT_STATS_JSON}")
    with open(OUTPUT_STATS_JSON, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print("✅ Done.")
    print(f"   - cases_chunked: {stats['cases_chunked']}/{stats['cases_total']}")
    print(f"   - chunks_raw: {stats['chunks_total_raw']}")
    print(f"   - chunks_saved: {len(chunks_df)}")
    print(f"   - dropped_quality: {stats['chunks_dropped_quality']}")
    print(f"   - dropped_dup_exact: {stats['chunks_dropped_duplicate_exact']}")
    print(f"   - dropped_dup_near: {stats['chunks_dropped_duplicate_near']}")
    print("   - chunks_by_section:", stats["chunks_by_section"])

if __name__ == "__main__":
    run_pipeline()
