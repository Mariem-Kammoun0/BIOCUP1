# backend/embedding/rebuild_input_embeddings.py
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]  # BIOCUP1
CHUNKS_DIR = PROJECT_ROOT / "data" / "input" / "chunks"
EMB_DIR = PROJECT_ROOT / "data" / "input" / "embeddings"

CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
EMB_DIR.mkdir(parents=True, exist_ok=True)


REQUIRED_META_COLS = [
    "chunk_id",
    "case_id",
    "primary_site",
    "tcga_type",
    "patient_id",
    "section",
    "original_section",
    "chunk_index",
    "sub_index",
    "has_tnm",
    "has_size",
    "has_ihc",
    "has_lymph",
    "has_margins",
    "has_tumor_size_cue",
    "is_admin_noise",
    "chunk_text",
]


def _flags_from_section(section: str) -> Dict[str, int]:
    sec = (section or "GENERAL").upper()
    return {
        "has_tnm": 0,
        "has_size": 0,
        "has_ihc": 1 if sec == "IHC" else 0,
        "has_lymph": 1 if sec in ("LYMPH_NODES", "LYMPH") else 0,
        "has_margins": 1 if sec == "MARGINS" else 0,
        "has_tumor_size_cue": 1 if sec in ("SYNOPTIC", "DIAGNOSIS") else 0,
        "is_admin_noise": 0,
    }


def write_input_chunks_csv(
    sections: List[Dict[str, Any]],
    out_csv: Optional[Path] = None,
    patient_id: str = "P_INPUT",
) -> Path:
    """
    sections = [
      {"section": "DIAGNOSIS", "text": "..."},
      {"section": "IHC", "text": "..."},
      ...
    ]
    """
    out_csv = out_csv or (CHUNKS_DIR / "input_chunks.csv")

    rows = []
    for idx, s in enumerate(sections):
        sec = (s.get("section") or "GENERAL").upper()
        txt = str(s.get("chunk_text") or s.get("text") or "").strip()
        if not txt:
            continue

        flags = _flags_from_section(sec)

        rows.append({
            "chunk_id": f"INPUT_{idx:04d}",
            "case_id": "INPUT",
            "primary_site": "unknown",
            "tcga_type": "",
            "patient_id": patient_id,
            "section": sec,
            "original_section": sec,
            "chunk_index": idx,
            "sub_index": 0,
            **flags,
            "chunk_text": txt,
        })

    if not rows:
        raise ValueError("No non-empty sections to write to input_chunks.csv")

    df = pd.DataFrame(rows, columns=REQUIRED_META_COLS)
    df.to_csv(out_csv, index=False)
    return out_csv


def rebuild_embeddings_from_sections(
    sections: List[Dict[str, Any]],
    patient_id: str = "P_INPUT",
) -> None:
    """
    1) writes input_chunks.csv
    2) runs dense.py then sparse.py (your existing scripts)
    """
    csv_path = write_input_chunks_csv(sections=sections, patient_id=patient_id)
    print("✅ Wrote input chunks:", csv_path)

    py = sys.executable  # current venv python
    dense_py = PROJECT_ROOT / "backend" / "embedding" / "dense.py"
    sparse_py = PROJECT_ROOT / "backend" / "embedding" / "sparse.py"

    # Run scripts with PROJECT_ROOT as CWD so relative paths won't break
    subprocess.run([py, str(dense_py)], check=True, cwd=str(dense_py.parent))
    subprocess.run([py, str(sparse_py)], check=True, cwd=str(sparse_py.parent))

    cwd=str(PROJECT_ROOT / "backend" / "embedding")


    print("✅ Rebuilt embeddings in:", EMB_DIR)
