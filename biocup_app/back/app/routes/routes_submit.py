from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from bson import ObjectId
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import os
import uuid
from pathlib import Path

from ..auth import get_current_user_id
from ..db import patients_col, revisions_col
from ..models import PatientForm, RevisionOut

router = APIRouter(prefix="/patients", tags=["revisions"])

# =========================
# Upload config (local disk)
# =========================
UPLOAD_ROOT = Path("uploads")  # you can change this
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_IMAGE_MB = 15


# ---------- Helpers ----------
def oid(s: str) -> ObjectId:
    try:
        return ObjectId(s)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid patient_id")


async def find_patient_owned(patient_id: str, doctor_id: str) -> Optional[Dict[str, Any]]:
    """
    Handles the common mismatch: doctor_id stored as string OR ObjectId in Mongo.
    We'll accept either.
    """
    patient_oid = oid(patient_id)

    # 1) doctor_id stored as string
    doc = await patients_col.find_one({"_id": patient_oid, "doctor_id": doctor_id})
    if doc:
        return doc

    # 2) doctor_id stored as ObjectId
    try:
        doctor_oid = ObjectId(doctor_id)
        doc = await patients_col.find_one({"_id": patient_oid, "doctor_id": doctor_oid})
        return doc
    except Exception:
        return None


def build_patient_report(case_id: str, form: Dict[str, Any]) -> str:
    """
    Generates a BIOCUP-like pseudo-report from the structured form.
    """
    ihc = form.get("ihc") or {}
    ihc_lines = [f"{k}: {v}" for k, v in ihc.items() if v]

    metastasis = form.get("metastasis_sites") or []
    metastasis_txt = ", ".join(metastasis) if metastasis else "Not specified"

    parts: List[str] = []

    parts.append(
        f"[case_id={case_id} | section=DIAGNOSIS]\n"
        f"Histology: {form.get('histology') or 'Not specified'}.\n"
        f"Metastasis sites: {metastasis_txt}.\n"
        f"Primary tumor site not identified.\n"
    )

    parts.append(
        f"[case_id={case_id} | section=LYMPH_NODES]\n"
        f"{form.get('lymph_nodes_summary') or 'No lymph node information provided.'}\n"
    )

    parts.append(
        f"[case_id={case_id} | section=IHC]\n"
        f"{('Immunohistochemistry: ' + '; '.join(ihc_lines)) if ihc_lines else 'No IHC provided.'}\n"
    )

    parts.append(
        f"[case_id={case_id} | section=TNM]\n"
        f"{form.get('tnm') or 'TNM not provided.'}\n"
    )

    parts.append(
        f"[case_id={case_id} | section=COMMENT]\n"
        f"{form.get('notes') or 'No additional comments.'}\n"
    )

    # mini-clean (same spirit as your pipeline)
    return " ".join("\n".join(parts).replace("\r", " ").split())


def compute_flags(text: str) -> Dict[str, bool]:
    t = text.lower()
    return {
        "has_tnm": any(x in t for x in ["pt", "pn", "pm", "tnm", "t0", "t1", "t2", "t3", "t4", "n0", "n1", "n2", "m1"]),
        "has_size": " cm" in t or " mm" in t,
        "has_ihc": "immuno" in t or " ck" in t or "ttf" in t or "cdx2" in t or "p63" in t,
        "has_lymph": "lymph" in t or " node" in t,
        "has_margins": "margin" in t,
    }


def split_sections_to_chunks(report_text: str) -> List[Dict[str, Any]]:
    """
    MVP: 1 chunk per section block. Later you can replace with your BioCUP chunker.
    """
    chunks: List[Dict[str, Any]] = []
    blocks = report_text.split("[case_id=")

    for b in blocks:
        b = b.strip()
        if not b:
            continue

        chunk_text = "[case_id=" + b
        section = "UNKNOWN"
        if "| section=" in chunk_text:
            section = chunk_text.split("| section=")[1].split("]")[0].strip()

        chunks.append({
            "section": section,
            "chunk_index": len(chunks),
            "chunk_text": chunk_text,
            **compute_flags(chunk_text),
        })

    return chunks


async def get_next_revision(patient_id: str, doctor_id: str) -> int:
    last = await revisions_col.find(
        {"patient_id": patient_id, "doctor_id": doctor_id}
    ).sort("revision", -1).to_list(length=1)

    return (last[0]["revision"] + 1) if last else 1


def _validate_image(file: UploadFile):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {file.content_type}")
    # size check is tricky with UploadFile streams; we enforce after reading bytes in save.


async def save_images(
    patient_id: str,
    doctor_id: str,
    revision: int,
    images: Optional[List[UploadFile]],
) -> List[Dict[str, Any]]:
    """
    Saves uploaded images to disk and returns metadata list to store in Mongo.
    """
    if not images:
        return []

    out: List[Dict[str, Any]] = []
    folder = UPLOAD_ROOT / "revisions" / doctor_id / patient_id / f"R{revision}"
    folder.mkdir(parents=True, exist_ok=True)

    for img in images:
        _validate_image(img)
        content = await img.read()
        if len(content) > MAX_IMAGE_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"Image too large (>{MAX_IMAGE_MB}MB): {img.filename}")

        ext = Path(img.filename).suffix.lower() or ".png"
        image_id = uuid.uuid4().hex
        filename = f"{image_id}{ext}"
        path = folder / filename

        with open(path, "wb") as f:
            f.write(content)

        out.append({
            "image_id": image_id,
            "filename": img.filename,
            "stored_filename": filename,
            "content_type": img.content_type,
            "size_bytes": len(content),
            "storage": "local",
            "relative_path": str(path).replace("\\", "/"),
            # optional: you can build a URL if you serve UPLOAD_ROOT as static
            "url": f"/{str(path).replace('\\', '/')}",
            "created_at": datetime.utcnow(),
        })

    return out


# =========================================================
# Endpoints (JSON) - keep your current ones
# =========================================================

@router.post("/{patient_id}/submit", response_model=RevisionOut)
async def submit_patient(
    patient_id: str,
    form: PatientForm,
    doctor_id: str = Depends(get_current_user_id),
):
    patient = await find_patient_owned(patient_id, doctor_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    next_rev = await get_next_revision(patient_id, doctor_id)
    case_id = f"PATIENT_{patient_id}_R{next_rev}"

    # ✅ form_data already contains ALL fields of PatientForm (whatever they are)
    form_dict = form.model_dump()
    report_text = build_patient_report(case_id, form_dict)
    chunks = split_sections_to_chunks(report_text)

    now = datetime.utcnow()
    rev_doc = {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "revision": next_rev,

        # status + timestamps
        "status": "submitted",
        "created_at": now,
        "updated_at": now,

        # ✅ store ALL form fields (complete)
        "form_data": form_dict,

        # generated text + chunks
        "generated_report_text": report_text,
        "chunks": chunks,

        # ✅ images field (empty for JSON endpoint)
        "images": [],

        # indexing
        "index_status": "not_indexed",
        "error": None,
    }
    await revisions_col.insert_one(rev_doc)

    await patients_col.update_one(
        {"_id": oid(patient_id)},
        {"$set": {"active_revision": next_rev, "updated_at": now}},
    )

    return RevisionOut(
        patient_id=patient_id,
        revision=next_rev,
        index_status=rev_doc["index_status"],
        created_at=rev_doc["created_at"],
    )


@router.get("/{patient_id}/revisions", response_model=List[RevisionOut])
async def list_revisions(
    patient_id: str,
    doctor_id: str = Depends(get_current_user_id),
):
    patient = await find_patient_owned(patient_id, doctor_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    cur = revisions_col.find(
        {"patient_id": patient_id, "doctor_id": doctor_id}
    ).sort("revision", -1)

    out: List[RevisionOut] = []
    async for d in cur:
        out.append(RevisionOut(
            patient_id=d["patient_id"],
            revision=d["revision"],
            index_status=d.get("index_status", "not_indexed"),
            created_at=d["created_at"],
        ))
    return out


@router.get("/{patient_id}/revisions/{rev}")
async def get_revision(
    patient_id: str,
    rev: int,
    doctor_id: str = Depends(get_current_user_id),
):
    patient = await find_patient_owned(patient_id, doctor_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    d = await revisions_col.find_one(
        {"patient_id": patient_id, "doctor_id": doctor_id, "revision": rev}
    )
    if not d:
        raise HTTPException(status_code=404, detail="Revision not found")

    d["_id"] = str(d["_id"])
    return d


@router.put("/{patient_id}/revisions/{rev}")
async def update_revision(
    patient_id: str,
    rev: int,
    form: PatientForm,
    doctor_id: str = Depends(get_current_user_id),
):
    patient = await find_patient_owned(patient_id, doctor_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    d = await revisions_col.find_one(
        {"patient_id": patient_id, "doctor_id": doctor_id, "revision": rev}
    )
    if not d:
        raise HTTPException(status_code=404, detail="Revision not found")

    form_dict = form.model_dump()  # ✅ ALL fields
    case_id = f"PATIENT_{patient_id}_R{rev}"
    report_text = build_patient_report(case_id, form_dict)
    chunks = split_sections_to_chunks(report_text)

    now = datetime.utcnow()

    await revisions_col.update_one(
        {"_id": d["_id"]},
        {"$set": {
            "updated_at": now,
            "status": "updated",
            "form_data": form_dict,
            "generated_report_text": report_text,
            "chunks": chunks,
            "error": None,
        }},
    )

    await patients_col.update_one(
        {"_id": oid(patient_id)},
        {"$set": {"active_revision": rev, "updated_at": now}},
    )

    updated = await revisions_col.find_one({"_id": d["_id"]})
    updated["_id"] = str(updated["_id"])
    return updated


# =========================================================
# NEW Endpoints (Multipart) - accepts images + form JSON
# Your front sends:
#   form: JSON.stringify(payload)
#   images: multiple files
# =========================================================

@router.post("/{patient_id}/submit-multipart")
async def submit_patient_multipart(
    patient_id: str,
    form: str = Form(...),
    images: Optional[List[UploadFile]] = File(default=None),
    doctor_id: str = Depends(get_current_user_id),
):
    patient = await find_patient_owned(patient_id, doctor_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    try:
        form_dict = json.loads(form) if form else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in 'form' field")

    # ✅ validate against PatientForm
    try:
        form_obj = PatientForm(**form_dict)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    next_rev = await get_next_revision(patient_id, doctor_id)
    case_id = f"PATIENT_{patient_id}_R{next_rev}"

    form_dict = form_obj.model_dump()  # ✅ ALL fields
    report_text = build_patient_report(case_id, form_dict)
    chunks = split_sections_to_chunks(report_text)

    # ✅ save images and store metadata
    images_meta = await save_images(patient_id, doctor_id, next_rev, images)

    now = datetime.utcnow()
    rev_doc = {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "revision": next_rev,

        "status": "submitted",
        "created_at": now,
        "updated_at": now,

        "form_data": form_dict,
        "generated_report_text": report_text,
        "chunks": chunks,

        # ✅ store images metadata in Mongo
        "images": images_meta,

        "index_status": "not_indexed",
        "error": None,
    }
    ins = await revisions_col.insert_one(rev_doc)

    await patients_col.update_one(
        {"_id": oid(patient_id)},
        {"$set": {"active_revision": next_rev, "updated_at": now}},
    )

    rev_doc["_id"] = str(ins.inserted_id)
    return rev_doc


@router.put("/{patient_id}/revisions/{rev}/multipart")
async def update_revision_multipart(
    patient_id: str,
    rev: int,
    form: str = Form(...),
    images: Optional[List[UploadFile]] = File(default=None),
    doctor_id: str = Depends(get_current_user_id),
):
    patient = await find_patient_owned(patient_id, doctor_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    d = await revisions_col.find_one(
        {"patient_id": patient_id, "doctor_id": doctor_id, "revision": rev}
    )
    if not d:
        raise HTTPException(status_code=404, detail="Revision not found")

    try:
        form_dict_raw = json.loads(form) if form else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in 'form' field")

    # ✅ validate against PatientForm
    try:
        form_obj = PatientForm(**form_dict_raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    form_dict = form_obj.model_dump()  # ✅ ALL fields
    case_id = f"PATIENT_{patient_id}_R{rev}"
    report_text = build_patient_report(case_id, form_dict)
    chunks = split_sections_to_chunks(report_text)

    # ✅ save new images (append to existing)
    new_images_meta = await save_images(patient_id, doctor_id, rev, images)
    old_images = d.get("images", []) or []
    merged_images = old_images + new_images_meta

    now = datetime.utcnow()

    await revisions_col.update_one(
        {"_id": d["_id"]},
        {"$set": {
            "updated_at": now,
            "status": "updated",
            "form_data": form_dict,
            "generated_report_text": report_text,
            "chunks": chunks,
            "images": merged_images,   # ✅ includes old + newly uploaded images
            "error": None,
        }},
    )

    await patients_col.update_one(
        {"_id": oid(patient_id)},
        {"$set": {"active_revision": rev, "updated_at": now}},
    )

    updated = await revisions_col.find_one({"_id": d["_id"]})
    updated["_id"] = str(updated["_id"])
    return updated
