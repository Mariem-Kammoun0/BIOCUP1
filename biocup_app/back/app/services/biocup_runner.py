# biocup_runner.py
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import pandas as pd
from bson import ObjectId

from app.db import revisions_col, patients_col  # adapt if needed


# ============================================================
# CONFIG — ADAPT THESE PATHS TO YOUR REAL PROJECT
# ============================================================

# Repo root = BIOCUP1
BIOCUP1_ROOT = Path(__file__).resolve().parents[4]

# Scripts (pipeline legacy)
CHUNKER_SCRIPT = (BIOCUP1_ROOT / "backend" / "chunking" / "chunker.py").resolve()
DENSE_EMBED_SCRIPT = (BIOCUP1_ROOT / "backend" / "embedding" / "dense.py").resolve()
SPARSE_EMBED_SCRIPT = (BIOCUP1_ROOT / "backend" / "embedding" / "sparse.py").resolve()
SEARCH_SCRIPT = (BIOCUP1_ROOT / "backend" / "search" / "search.py").resolve()
EXPLAIN_SCRIPT = (BIOCUP1_ROOT / "backend" / "search" / "explain.py").resolve()

# ✅ explain writes always here (fixed path)
EXPLAIN_OUTPUT_JSON = (BIOCUP1_ROOT / "backend" / "search" / "explain_output.json").resolve()

DEFAULT_PRIMARY_SITE = os.getenv("BIOCUP_DEFAULT_PRIMARY_SITE", "UNKNOWN")
DEFAULT_TCGA_TYPE = os.getenv("BIOCUP_DEFAULT_TCGA_TYPE", "UNKNOWN")

# ✅ IMPORTANT: Put the CSV exactly where your chunker expects it.
CHUNKER_INPUT_CSV = (BIOCUP1_ROOT / "backend" / "data" / "input" / "cases.csv").resolve()
CHUNKER_INPUT_CSV.parent.mkdir(parents=True, exist_ok=True)


# ============================================================
# Helpers
# ============================================================

def _now() -> datetime:
    return datetime.utcnow()

def _python_exec() -> str:
    # Use same python interpreter as FastAPI backend
    return sys.executable

def _run_cmd(cmd: list[str], cwd: Optional[Path] = None) -> Tuple[int, str]:
    # Force UTF-8 so emojis/unicode in scripts don't crash on Windows
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        env=env,
    )
    out, _ = proc.communicate()
    return proc.returncode, out or ""

def _ensure_file_exists(p: Path, label: str) -> None:
    if not p.exists():
        raise FileNotFoundError(f"{label} not found at: {p}")

def _generate_case_id() -> str:
    return f"CASE_{uuid.uuid4().hex}"

def _build_case_csv_row(
    *,
    case_id: str,
    patient_id: str,
    report_text: str,
    primary_site: str,
    tcga_type: str,
) -> pd.DataFrame:
    # REQUIRED_COLS expected by chunker:
    # ["case_id","primary_site","tcga_type","patient_id","report_text"]
    return pd.DataFrame([{
        "case_id": case_id,
        "primary_site": primary_site or DEFAULT_PRIMARY_SITE,
        "tcga_type": tcga_type or DEFAULT_TCGA_TYPE,
        "patient_id": patient_id,
        "report_text": report_text or "",
    }])

def _append_or_overwrite_input_csv(row_df: pd.DataFrame, path: Path) -> None:
    """
    Legacy-friendly:
    - If chunker expects a CSV of multiple rows, you can APPEND.
    - If it expects exactly 1 row, set mode='w' overwrite.
    Choose behavior by switching APPEND = True/False.
    """
    APPEND = False  # set True if you want to accumulate multiple cases

    if APPEND and path.exists():
        row_df.to_csv(path, mode="a", header=False, index=False)
    else:
        row_df.to_csv(path, mode="w", header=True, index=False)


# ============================================================
# Core runner
# ============================================================

async def run_biocup_pipeline(
    *,
    patient_id: str,
    revision: int,
    doctor_id: str,
) -> Dict[str, Any]:
    started_at = _now()

    # 1) Load revision from Mongo
    rev_doc = await revisions_col.find_one({
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "revision": revision,
    })
    if not rev_doc:
        raise RuntimeError("Revision not found for this patient/doctor/revision")

    report_text = rev_doc.get("generated_report_text") or ""
    if not report_text.strip():
        raise RuntimeError("generated_report_text is empty. Submit/update revision first.")

    # 2) Ensure case_id exists (persist once)
    case_id = rev_doc.get("case_id")
    if not case_id:
        case_id = _generate_case_id()
        await revisions_col.update_one(
            {"_id": rev_doc["_id"]},
            {"$set": {"case_id": case_id, "updated_at": _now()}},
        )

    # 3) Create the CSV exactly where chunker expects it
    df = _build_case_csv_row(
        case_id=case_id,
        patient_id=patient_id,
        report_text=report_text,
        primary_site=rev_doc.get("primary_site") or DEFAULT_PRIMARY_SITE,
        tcga_type=rev_doc.get("tcga_type") or DEFAULT_TCGA_TYPE,
    )
    _append_or_overwrite_input_csv(df, CHUNKER_INPUT_CSV)

    # Store pipeline state early
    await revisions_col.update_one(
        {"_id": rev_doc["_id"]},
        {"$set": {
            "biocup_pipeline": {
                "status": "running",
                "started_at": started_at,
                "input_csv": str(CHUNKER_INPUT_CSV).replace("\\", "/"),
            },
            "updated_at": _now(),
        }},
    )

    # 4) Validate scripts exist
    _ensure_file_exists(CHUNKER_SCRIPT, "Chunker script")
    _ensure_file_exists(DENSE_EMBED_SCRIPT, "Dense embedding script")
    _ensure_file_exists(SPARSE_EMBED_SCRIPT, "Sparse embedding script")
    _ensure_file_exists(SEARCH_SCRIPT, "Search script")
    _ensure_file_exists(EXPLAIN_SCRIPT, "Explain script")

    logs: Dict[str, str] = {}

    def run_script(name: str, script_path: Path) -> None:
        cmd = [_python_exec(), str(script_path)]
        rc, out = _run_cmd(cmd, cwd=script_path.parent)
        logs[name] = out
        if rc != 0:
            raise RuntimeError(f"{name} failed (exit={rc}). Output:\n{out}")

    # 5) Run pipeline steps — no env vars
    run_script("chunker", CHUNKER_SCRIPT)
    run_script("dense_embedding", DENSE_EMBED_SCRIPT)
    run_script("sparse_embedding", SPARSE_EMBED_SCRIPT)
    run_script("search", SEARCH_SCRIPT)
    run_script("explain", EXPLAIN_SCRIPT)

    # ✅ Read final JSON written by explain.py (fixed path)
    explain_json = None
    if EXPLAIN_OUTPUT_JSON.exists():
        try:
            explain_json = json.loads(EXPLAIN_OUTPUT_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            logs["explain_read_error"] = f"Failed to parse JSON: {e}"
    else:
        logs["explain_read_missing"] = f"Missing explain output file: {EXPLAIN_OUTPUT_JSON}"

    finished_at = _now()

    pipeline_doc = {
        "status": "done",
        "started_at": started_at,
        "finished_at": finished_at,
        "input_csv": str(CHUNKER_INPUT_CSV).replace("\\", "/"),
        "outputs": {
            "explain_json_path": str(EXPLAIN_OUTPUT_JSON).replace("\\", "/"),
            "explain_json": explain_json,
        },
        "logs": {k: (v[-20000:] if isinstance(v, str) else "") for k, v in logs.items()},
    }

    await revisions_col.update_one(
        {"_id": rev_doc["_id"]},
        {"$set": {"biocup_pipeline": pipeline_doc, "updated_at": _now()}},
    )

    return pipeline_doc


# CLI debug
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python biocup_runner.py <patient_id> <revision:int> <doctor_id>")
        sys.exit(1)

    p_id = sys.argv[1]
    rev = int(sys.argv[2])
    d_id = sys.argv[3]

    async def _main():
        out = await run_biocup_pipeline(patient_id=p_id, revision=rev, doctor_id=d_id)
        print(json.dumps(out, default=str, indent=2))

    asyncio.run(_main())
