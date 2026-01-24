# ============================================================
# BioCUP — Clinically reliable semantic chunking (1 row = 1 case)
# ✅ Goal: clinically coherent chunks (SPECIMEN / DIAGNOSIS / LYMPH / SYNOPTIC / MARGINS / IHC / COMMENT / GROSS / MICRO)
# ✅ Fixes:
#   1) Protect enumerations (1., 2–7., 8.) BEFORE chunking + BEFORE post-split
#   2) Post-split is ITEM-first (preserves "2-7.") + NO dropping short segments (merge instead)
#   3) Better sentence split (no split on ":" to avoid broken parentheses / labels)
#   4) Fix OCR TNM: pT2NO -> pT2N0, pNO -> pN0
#   5) Fix cassette regex so it DOES NOT delete T2/N0/M1
#   6) SPECIMEN dominance improved to keep inventories under SPECIMEN
#   7) Auto-create output directory
# ============================================================

import os
import re
import json
import hashlib
import pandas as pd
from typing import Dict, List, Any, Tuple

from chonkie import SemanticChunker
from chonkie.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from text_cleaner import clean_medical_report 

# =========================
# CONFIG
# =========================
INPUT_CSV = "../../../data/raw/biocup_subset.csv"
OUTPUT_CSV = "../../../data/chunking/biocup_chunks.csv"
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
# HEADINGS
# =========================
RAW_HEADERS = [
    "FINAL DIAGNOSIS", "DIAGNOSIS",
    "INTERPRETATION AND DIAGNOSIS", "CLINICAL HISTORY", "CLINICAL NOTES",
    "HISTORY", "SPECIMEN", "SPECIMENS SUBMITTED",
    "SPECIMENS RECEIVED", "PROCEDURE", "OPERATION",
    "GROSS DESCRIPTION", "GROSS",
    "MICROSCOPIC DESCRIPTION", "MICROSCOPIC",
    "MICRO", "SYNOPTIC REPORT", "SYNOPTIC",
    "CAP SYNOPTIC", "IMMUNOHISTOCHEMISTRY",
    "IMMUNOHISTOCHEMICAL", "IHC", "COMMENT", "COMMENTS",
    "NOTE", "NOTES",
    "INTRA OPERATIVE CONSULTATION",
    "INTRAOPERATIVE CONSULTATION",
    "FROZEN SECTION", "SPECIAL STAINS",
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
# CLEANING
# =========================
_PAGE_RE = re.compile(r"(?i)\bpage\s*:?\s*\d+\s*(of\s*\d+)?\b")
_STATUS_RE = re.compile(r"(?i)\bstatus\s*:\s*corrected\b.*?(?=(\.\s)|$)")
_RULE_RE = re.compile(r"(=|-|_){3,}")
_WS_RE = re.compile(r"[ \t]+")

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

# ✅ FIX: don't delete TNM tokens like T2 / N0 / M1
# keep cassette-like codes A1, B12 ... but NOT T2/N0/M1
_CASSETTE_RE = re.compile(r"\b(?![TNM]\d)[A-HJ-Z]\d{1,2}\b")


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
# OCR NORMALIZATION (TNM)
# =========================
def normalize_tnm_ocr(t: str) -> str:
    if not t:
        return ""

    # pNO -> pN0
    t = re.sub(r"(?i)\bpN\s*O\b", "pN0", t)

    # Only fix "NO" when it clearly belongs to TNM (near T/N/M tokens)
    t = re.sub(r"(?i)\b(p?N)\s*O\b", r"\1 0", t)  # N O -> N 0 (rare OCR)
    t = re.sub(r"(?i)\b(pT\d+[a-c]?)\s*NO\b", r"\1N0", t)  # pT2NO -> pT2N0
    t = re.sub(r"(?i)\b(T\d+[a-c]?)\s*NO\b", r"\1N0", t)   # T2NO -> T2N0

    # Also handle "pNO:" forms
    t = re.sub(r"(?i)\bpN0\b", "pN0", t)  # keep consistent if needed

    return t

# =========================
# SECTION SPLITTING
# =========================
HEAD_RE = re.compile(
    r"(?im)^(?P<h>(" + "|".join(map(re.escape, RAW_HEADERS)) + r"))\s*[:\-]?\s*(?P<rest>.*)$"
)
INLINE_DIAG_RE = re.compile(r"(?i)\bDIAGNOSIS\b\s*[:.]")

def split_by_sections(report_text: str) -> List[Dict[str, str]]:
    t = clean_text_keep_lines(report_text)
    if not t:
        return []

    # Inline DIAGNOSIS
    if INLINE_DIAG_RE.search(t):
        pre, post = re.split(INLINE_DIAG_RE, t, maxsplit=1)
        sections = []
        if pre.strip():
            sections.append({"section": "GENERAL", "text": clean_text_flat(pre)})
        if post.strip():
            sections.append({"section": "DIAGNOSIS", "text": clean_text_flat(post)})
        return sections

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
        body_flat = normalize_tnm_ocr(body_flat)

        if not body_flat:
            continue

        if (
            len(body_flat) >= 120 or
            re.search(r"(?i)\b(?:pT|pN|ypT|ypN)\b|immuno|margin|lymph node|metast|\bcm\b|\bmm\b", body_flat)
        ):
            out.append({"section": bucket, "text": body_flat})

    return out if out else [{"section": "GENERAL", "text": normalize_tnm_ocr(clean_text_flat(t))}]

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
# FLAGS
# =========================
_IHC_RE = re.compile(
    r"\b(?:CK\d+|AE1/AE3|CK5/6|TTF-?1|p63|p40|NAPSIN(?:-?A)?|PAX8|WT1|HER2|ER\b|PR\b|ALK\b|ROS1\b|PD-?L1\b|EGFR\b|CK7\b)\b",
    re.I
)

_TNM_RE = re.compile(
    r"(?i)\b(?:p|yp)?T\s*\d+[a-c]?\b|\b(?:p|yp)?N\s*\d+[a-c]?\b|\b(?:p|yp)?M\s*\d+[a-c]?\b|\bT\d+[a-c]?\s*N\d+[a-c]?\b"
)

_MEASURE_RE = re.compile(
    r"(?i)\b\d+(?:\.\d+)?\s*(?:cm|mm)\b|\b\d+(?:\.\d+)?\s*x\s*\d+(?:\.\d+)?(?:\s*x\s*\d+(?:\.\d+)?)?\s*(?:cm|mm)\b"
)

_TUMOR_SIZE_CUE_RE = re.compile(
    r"(?i)\b(tumou?r\s+size|maximum\s+tumou?r\s+dimension|greatest\s+dimension|size\s+of\s+tumou?r)\b"
)

_MARGIN_RE = re.compile(
    r"(?i)\bmargin(?:s)?\b|\bresection\s+margin\b|\bclosest\s+margin\b|\bdistance\s+of\b|\bdistance\s+from\b|\bstapled\s+parenchymal\b|\bbronchial\s+resection\s+margin\b"
)

_LYMPH_RE = re.compile(
    r"(?i)\blymph\s+node(?:s)?\b|\bnodal\b|\bstation\b|\bST\s*\d+\w*\b|\bsubcarinal\b|\bparatracheal\b|\binterlobar\b|\blobar\b|\bhilar\b|\bmediastin(?:al|um)\b"
)

_GROSS_CUES = re.compile(r"(?i)\b(gross|received\s+(fresh|in\s+formalin)|measuring|weighing|inked|pleural\s+surface|sectioning|submitted)\b")
_MICRO_CUES = re.compile(r"(?i)\b(microscopic|histologic|histologic\s+grade|grade\s*[:\-]|visceral\s+pleural|lymphovascular|perineural|mitos(?:is|es)|cytologic)\b")

_ADMIN_CUES = re.compile(
    r"(?i)\b(electronic(?:ally)?\s+signed|distributed\s+to|print\s+date|verified:|continued\s+on\s+next\s+page|"
    r"slides?\s+received|reported\s+\d{1,2}\.\d{1,2}\s*(?:am|pm)|tissue\s+bank|ischemic\s+time)\b"
)

# ✅ Stronger specimen cues (inventory patterns)
_SPECIMEN_CUES = re.compile(
    r"(?im)\b("
    r"specimen(?:s)?\s*(?:received|submitted)?|specimens?\s+(?:are|were)\s+received|"
    r"container labeled|labeled\s+as|submitted in toto|representative sections|"
    r"cassette|block|part\s+[A-Z]\b|"
    r"(?:^|\s)(?:[A-Z]\.|[0-9]+\.)\s*(?:lymph\s+nodes?|lung|colon|breast|skin|biopsy|resection|lobectomy|wedge)"
    r")\b"
)

def compute_flags(text: str) -> Dict[str, bool]:
    t = normalize_tnm_ocr(text or "")
    has_measure = bool(_MEASURE_RE.search(t))
    has_tumor_size = bool(_TUMOR_SIZE_CUE_RE.search(t)) and has_measure
    return {
        "has_tnm": bool(_TNM_RE.search(t)),
        "has_size": has_measure,
        "has_ihc": bool(_IHC_RE.search(t)),
        "has_lymph": bool(_LYMPH_RE.search(t)),
        "has_margins": bool(_MARGIN_RE.search(t)),
        "has_tumor_size_cue": has_tumor_size,
    }

# =========================
# ROUTER
# =========================
def _count(rex: re.Pattern, t: str) -> int:
    return len(rex.findall(t or ""))

def route_section(original: str, chunk: str) -> str:
    orig = original or "GENERAL"
    t = normalize_tnm_ocr(chunk or "")
    low = t.lower()

    # ADMIN
    if _ADMIN_CUES.search(t) and len(t) < 700 and not _TNM_RE.search(t):
        return "ADMIN"

    # ✅ SPECIMEN dominance first (prevents inventory -> LYMPH_NODES)
    if orig in {"GENERAL", "SPECIMEN"} and _SPECIMEN_CUES.search(t):
        return "SPECIMEN"
    if "specimen" in low and "received" in low:
        return "SPECIMEN"

    # ✅ Hard TNM -> SYNOPTIC
    if _TNM_RE.search(t) and (_count(_TNM_RE, t) >= 2 or "pathologic stage" in low or "synoptic" in low):
        return "SYNOPTIC"

    scores = {
        "IHC": _count(_IHC_RE, t) + (2 if "immunohistochem" in low else 0),
        "SYNOPTIC": _count(_TNM_RE, t) + (2 if "pathologic stage" in low else 0) + (1 if "synoptic" in low else 0),
        "MARGINS": _count(_MARGIN_RE, t),
        "LYMPH_NODES": _count(_LYMPH_RE, t),
        "GROSS": (2 if _GROSS_CUES.search(t) else 0) + (1 if "measuring" in low else 0),
        "MICRO": (2 if _MICRO_CUES.search(t) else 0) + (1 if "histologic" in low else 0),
    }

    preserve = orig in {"DIAGNOSIS", "COMMENT", "CLINICAL_HISTORY", "SPECIMEN"}

    best_section, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score == 0:
        return orig if preserve else "GENERAL"

    priority = ["IHC", "SYNOPTIC", "MARGINS", "LYMPH_NODES", "MICRO", "GROSS"]
    tied = [sec for sec, sc in scores.items() if sc == best_score and sc > 0]
    if len(tied) > 1:
        for p in priority:
            if p in tied:
                best_section = p
                break

    if preserve and best_score <= 1:
        return orig

    return best_section

# =========================
# PROTECT ENUMERATIONS
# =========================
_ITEM_MARK = "<ITEM>"

# Detect:
#  - "1. ", "2) "
#  - "2-7. ", "2–7. "
_ENUM_RE = re.compile(r"(?m)(^|\s)(\d+\s*[-–]\s*\d+|\d+)\s*[\.\)]\s+")

def protect_enumerations(text: str) -> str:
    if not text:
        return ""
    return _ENUM_RE.sub(lambda m: f"{m.group(1)}{_ITEM_MARK} {m.group(2)}. ", text)

def unprotect_enumerations(text: str) -> str:
    return (text or "").replace(_ITEM_MARK, "").strip()

# =========================
# PROTECT SUB-ITEMS (a), b), i), ii))
# =========================
_SUB_MARK = "<SUB>"
_SUB_RE = re.compile(r"(?i)(^|[\s:;,\(])([a-h])\)\s+")


def protect_subitems(text: str) -> str:
    if not text:
        return ""
    return _SUB_RE.sub(
        lambda m: f"{m.group(1)}{_SUB_MARK} {m.group(2).lower()}) ",
        text,
    )

def unprotect_subitems(text: str) -> str:
    return (text or "").replace(_SUB_MARK, "").strip()


# =========================
# POST-SPLIT (ITEM-FIRST)
# =========================
# ✅ FIX: don't split on ":" (causes broken parentheses & labels)
_SENT_SPLIT_RE = re.compile(r"(?<=[\.\;])\s+")

def _concept_label(s: str) -> str:
    s = normalize_tnm_ocr(s or "")
    low = s.lower()
    if _ADMIN_CUES.search(s):
        return "ADMIN"
    if _IHC_RE.search(s) or "immunohistochem" in low:
        return "IHC"
    if _TNM_RE.search(s) or "pathologic stage" in low or "synoptic" in low:
        return "SYNOPTIC"
    if _MARGIN_RE.search(s):
        return "MARGINS"
    if _SPECIMEN_CUES.search(s):
        return "SPECIMEN"
    if _LYMPH_RE.search(s):
        return "LYMPH_NODES"
    if _GROSS_CUES.search(s):
        return "GROSS"
    if _MICRO_CUES.search(s):
        return "MICRO"
    return "GENERAL"

def _split_by_items(text: str) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    if _ITEM_MARK not in t:
        return [t]
    parts = [p.strip() for p in t.split(_ITEM_MARK) if p.strip()]
    return parts

def _sentence_group_if_mixed(text: str) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    sents = [s.strip() for s in _SENT_SPLIT_RE.split(t) if s.strip()]
    if len(sents) <= 1:
        return [t]

    labels = [_concept_label(s) for s in sents]
    if len(set(labels)) == 1:
        return [t]

    # bucket contiguous sentences by label
    out: List[str] = []
    buf = sents[0]
    cur_lab = labels[0]
    for s, lab in zip(sents[1:], labels[1:]):
        if lab == cur_lab and len(buf) + len(s) < 900:
            buf = (buf + " " + s).strip()
        else:
            out.append(buf)
            buf = s
            cur_lab = lab
    if buf:
        out.append(buf)

    # merge tiny fragments instead of dropping
    merged: List[str] = []
    for seg in out:
        if merged and len(seg) < 120:
            merged[-1] = (merged[-1] + " " + seg).strip()
        else:
            merged.append(seg)

    return merged if merged else [t]
def _split_by_subitems(text: str) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    if _SUB_MARK not in t:
        return [t]
    return [p.strip() for p in t.split(_SUB_MARK) if p.strip()]


def post_split_medical(chunk_text: str) -> List[str]:
    t = normalize_tnm_ocr((chunk_text or "").strip())
    if not t:
        return []

    # 1) item-first split
    # 1) item-first split (1., 2-7., etc) + subitems (a), b))
    items = []
    for it in _split_by_items(t):
        items.extend(_split_by_subitems(it))


    # if single block, split by sentences only if mixed
    if len(items) == 1:
        return _sentence_group_if_mixed(items[0])

    # 2) label items
    labeled: List[Tuple[str, str]] = [(it, _concept_label(it)) for it in items]

    # 3) group contiguous items by label
    groups: List[Tuple[str, List[str]]] = []
    cur_lab = labeled[0][1]
    cur = [labeled[0][0]]
    for it, lab in labeled[1:]:
        if lab == cur_lab:
            cur.append(it)
        else:
            groups.append((cur_lab, cur))
            cur_lab = lab
            cur = [it]
    groups.append((cur_lab, cur))

    # 4) merge tiny groups into previous (avoid fragmenting)
    merged_blocks: List[str] = []
    for lab, segs in groups:
        block = " ".join(segs).strip()
        if merged_blocks and len(block) < 140:
            merged_blocks[-1] = (merged_blocks[-1] + " " + block).strip()
        else:
            merged_blocks.append(block)

    # 5) final: sentence grouping only if mixed
    out: List[str] = []
    for block in merged_blocks:
        out.extend(_sentence_group_if_mixed(block))

    # ✅ FIX: never drop small segments blindly; merge them
    out2: List[str] = []
    for seg in out:
        seg = seg.strip()
        if not seg:
            continue
        if out2 and len(seg) < 90:
            out2[-1] = (out2[-1] + " " + seg).strip()
        else:
            out2.append(seg)

    # keep only chunks that satisfy global quality
    # --- NEW: don't drop a tiny first segment; merge it forward
    if out2 and len(unprotect_enumerations(out2[0])) < MIN_CHARS_PER_CHUNK and len(out2) > 1:
        merged0 = (out2[0] + " " + out2[1]).strip()
        out2 = [merged0] + out2[2:]

    final = [x for x in out2 if quality_ok(unprotect_enumerations(x))]


    return final if final else [t]

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
    # avoid rejecting short staging-like chunks too aggressively
    if len(s2) > 300 and len(set(s2)) < 12:
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

def paren_balance(s: str) -> int:
    s = s or ""
    return s.count("(") - s.count(")")

def merge_until_parentheses_closed(
    chunks: List[str],
    max_chars: int = 2200,
    max_merge_steps: int = 8,
) -> List[str]:
    """
    Ensure no chunk ends with unbalanced '('.
    If a chunk has more '(' than ')', merge forward until balance is 0
    (or stop by safety limits).
    """
    out: List[str] = []
    i = 0

    while i < len(chunks):
        cur = (chunks[i] or "").strip()
        if not cur:
            i += 1
            continue

        bal = paren_balance(cur)

        if bal <= 0:
            out.append(cur)
            i += 1
            continue

        steps = 0
        j = i
        merged = cur

        while bal > 0 and j + 1 < len(chunks) and steps < max_merge_steps:
            nxt = (chunks[j + 1] or "").strip()
            if not nxt:
                j += 1
                steps += 1
                continue

            if len(merged) + 1 + len(nxt) > max_chars:
                break

            merged = (merged + " " + nxt).strip()
            bal = paren_balance(merged)
            j += 1
            steps += 1

        out.append(merged)
        i = j + 1

    # ✅ final pass: if any chunk still has open parens, try merge with next once
    final: List[str] = []
    i = 0
    while i < len(out):
        cur = out[i]
        if (
            paren_balance(cur) > 0
            and i + 1 < len(out)
            and len(cur) + 1 + len(out[i + 1]) <= max_chars
        ):
            final.append((cur + " " + out[i + 1]).strip())
            i += 2
        else:
            final.append(cur)
            i += 1

    return final

def merge_leading_bullets(chunks: List[str], max_chars: int) -> List[str]:
    """
    If a chunk starts with a bullet (- • *), attach it to the previous chunk
    (when it fits), because it's almost always a continuation.
    """
    out: List[str] = []
    for ch in chunks:
        ch = (ch or "").strip()
        if not ch:
            continue

        if (
            out
            and re.match(r"^[-•*]\s+", ch)
            and len(out[-1]) + 1 + len(ch) <= max_chars
        ):
            out[-1] = (out[-1] + " " + ch).strip()
        else:
            out.append(ch)

    return out

def bracket_balance(s: str) -> int:
    s = s or ""
    return s.count("[") - s.count("]")

def needs_merge(prev: str, nxt: str) -> bool:
    prev = (prev or "").strip()
    nxt = (nxt or "").strip()
    if not prev or not nxt:
        return False

    # A) delimiters not closed => MUST merge
    if paren_balance(prev) > 0:
        return True
    if bracket_balance(prev) > 0:
        return True

    # B) nxt clearly looks like continuation
    starts_lower = bool(re.match(r"^[a-z]", nxt))
    starts_roman = bool(re.match(r"^(?:i{1,3}|iv|v|vi{0,3}|ix|x)\)", nxt.lower()))
    starts_letter_item = bool(re.match(r"^[a-h]\)", nxt.lower()))  # a) b) c) ...
    starts_punct = bool(re.match(r"^[\)\],;:\-]\s*", nxt))
    starts_bullet = bool(re.match(r"^[-•*]\s+", nxt))

    # C) prev ends in "hanging" patterns
    prev_hanging = bool(re.search(r"(?:with\s*:|and|or)\s*\.\s*$", prev, re.I)) or prev.endswith(":")

    # D) special: nxt begins with ']' => definitely continuation of bracketed list
    starts_close_bracket = nxt.startswith("]")

    return (
        starts_close_bracket
        or starts_punct
        or starts_bullet
        or starts_roman
        or starts_letter_item
        or (starts_lower and not re.match(r"^\d+[\.\)]\s+", nxt))  # not a new numbered item
        or prev_hanging
    )

def merge_continuations(chunks: List[str], max_chars: int, max_steps: int = 8) -> List[str]:
    out: List[str] = []
    i = 0
    while i < len(chunks):
        cur = (chunks[i] or "").strip()
        if not cur:
            i += 1
            continue

        j = i
        steps = 0
        while j + 1 < len(chunks) and steps < max_steps:
            nxt = (chunks[j + 1] or "").strip()
            if not nxt:
                j += 1
                steps += 1
                continue

            if not needs_merge(cur, nxt):
                break

            if len(cur) + 1 + len(nxt) > max_chars:
                break

            cur = (cur + " " + nxt).strip()
            j += 1
            steps += 1

        out.append(cur)
        i = j + 1

    return out


# =========================
# MAIN PIPELINE
# =========================
def run_pipeline() -> None:
    print("📥 Loading CSV...")
    df = pd.read_csv(INPUT_CSV)
    
    #adding data cleaning
    # Appliquer la fonction à toute la colonne 'report_text'
    df["report_text"] = df["report_text"].apply(clean_medical_report)

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
        "errors_semantic_chunking": 0,
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
            sec_text = normalize_tnm_ocr(sec["text"])
            stats["sections_total"] += 1

            # Protect enumerations BEFORE any chunking or splitting
            safe_text = protect_enumerations(sec_text)

            # Decide whether to semantic-chunk
            NO_SEMANTIC_CHUNK_SECTIONS = {"GENERAL", "SPECIMEN"}
            DIAGNOSIS_LONG_THRESHOLD = 1200

            skip_semantic = (
                (orig_section in NO_SEMANTIC_CHUNK_SECTIONS)
                or (orig_section == "DIAGNOSIS" and len(safe_text) < DIAGNOSIS_LONG_THRESHOLD)
                or (len(safe_text) < 600)
            )

            if skip_semantic:
                chunks = [unprotect_enumerations(safe_text)]
            else:
                try:
                    chunks_obj = chunker.chunk(safe_text)

                    # Convert objects -> str and remove <ITEM>
                    raw_chunks = [unprotect_enumerations(chunk_to_text(c)) for c in chunks_obj]
                    # 1) merge until () and [] are closed + continuation heuristics
                    raw_chunks = merge_continuations(
                        raw_chunks,
                        max_chars=MAX_CHARS_PER_CHUNK,
                        max_steps=10
                    )


                    # 1) close parentheses by merging forward
                    raw_chunks = merge_until_parentheses_closed(
                        raw_chunks,
                        max_chars=MAX_CHARS_PER_CHUNK,
                        max_merge_steps=8,
                    )

                    # 2) attach bullet-leading chunks to previous chunk
                    raw_chunks = merge_leading_bullets(
                        raw_chunks,
                        max_chars=MAX_CHARS_PER_CHUNK,
                    )

                    chunks = raw_chunks

                except Exception as e:
                    stats["errors_semantic_chunking"] += 1
                    # fallback clean
                    chunks = [unprotect_enumerations(safe_text)]

            stats["chunks_total_raw"] += len(chunks)

            for chunk_index, raw_chunk in enumerate(chunks):
                raw_chunk = normalize_tnm_ocr((raw_chunk or "").strip())

                if not quality_ok(raw_chunk):
                    stats["chunks_dropped_quality"] += 1
                    continue

                # Post-split on PROTECTED version so "2-7." stays intact
                protected_for_split = protect_enumerations(raw_chunk)
                protected_for_split = protect_subitems(protected_for_split)

                concept_chunks = post_split_medical(protected_for_split)

                concept_chunks = [unprotect_subitems(x) for x in concept_chunks]

                for sub_index, cc in enumerate(concept_chunks):
                    cc = normalize_tnm_ocr(unprotect_enumerations(cc).strip())

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

                        if len(cc) < 220:
                            thr = 0.95
                        elif len(cc) < 320:
                            thr = 0.93
                        else:
                            thr = NEAR_DUP_SIM_THRESHOLD

                        if prev_sets and any(jaccard(ts, ps) >= thr for ps in prev_sets):
                            stats["chunks_dropped_duplicate_near"] += 1
                            continue

                        prev_sets.append(ts)
                        seen_token_sets[key] = prev_sets

                    prefix = build_context_prefix(row, routed_section)
                    chunk_text = prefix + cc
                    flags = compute_flags(cc)

                    all_rows.append({
                        "chunk_id": make_chunk_id(str(row["case_id"]), routed_section, int(chunk_index), int(sub_index), cc),
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
                        "is_admin_noise": (routed_section == "ADMIN"),
                    })

                    stats["chunks_total_after_postsplit"] += 1
                    stats["chunks_by_section"][routed_section] = stats["chunks_by_section"].get(routed_section, 0) + 1

    chunks_df = pd.DataFrame(all_rows)
    if chunks_df.empty:
        raise ValueError("No chunks produced. Check input and regex rules.")

    out_dir = os.path.dirname(OUTPUT_CSV)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

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
    print(f"   - semantic_errors: {stats['errors_semantic_chunking']}")
    print("   - chunks_by_section:", stats["chunks_by_section"])

if __name__ == "__main__":
    run_pipeline()
