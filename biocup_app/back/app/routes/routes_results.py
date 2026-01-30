# app/routes/routes_results.py
from fastapi import APIRouter, Depends, HTTPException

from bson import ObjectId

from datetime import datetime

from ..auth import get_current_user_id  
from ..db import revisions_col, results_col
from ..services.biocup_runner import run_biocup_pipeline

router = APIRouter(prefix="/results", tags=["results"])


@router.post("/{patient_id}/{revision}")
async def generate_results(
    patient_id: str,
    revision: int,
    doctor_id: str = Depends(get_current_user_id),
):
    revision_doc = await revisions_col.find_one({
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "revision": revision
    })

    if not revision_doc:
        raise HTTPException(status_code=404, detail="Revision not found")

    report_text = revision_doc.get("generated_report_text")
    if not report_text:
        raise HTTPException(status_code=400, detail="No generated report text")

    # ✅ Lancer le pipeline (IMPORTANT: await + doctor_id)
    pipeline_doc = await run_biocup_pipeline(
        patient_id=patient_id,
        revision=revision,
        doctor_id=doctor_id,
    )

    # ✅ Stocker dans nouvelle "table" (collection)
    result_doc = {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "revision": revision,
        "created_at": datetime.utcnow(),
        "pipeline": pipeline_doc,         # logs + paths + status
        # optionnel: snapshot du texte utilisé (utile pour audit)
        "generated_report_text": report_text,
    }
    ins = await results_col.insert_one(result_doc)

    # ✅ Retour front
    return {
        "result_id": str(ins.inserted_id),
        "patient_id": patient_id,
        "revision": revision,
        "status": pipeline_doc.get("status", "done"),
        "pipeline": pipeline_doc,
    }

@router.get("/{result_id}")
async def get_result(result_id: str, doctor_id: str = Depends(get_current_user_id)):
    try:
        oid = ObjectId(result_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid result_id")

    doc = await results_col.find_one({"_id": oid, "doctor_id": doctor_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Result not found")

    doc["_id"] = str(doc["_id"])
    return doc