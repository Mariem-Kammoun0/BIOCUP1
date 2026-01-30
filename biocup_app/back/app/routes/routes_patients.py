from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from datetime import datetime

from ..db import patients_col
from ..auth import get_current_user_id
from ..models import PatientCreate, PatientOut
from app.services.utils import date_to_datetime

router = APIRouter(prefix="/patients", tags=["patients"])


def to_out(doc) -> PatientOut:
    doc["dob"] = date_to_datetime(doc.get("dob"))
    return PatientOut(
        id=str(doc["_id"]),
        doctor_id=doc["doctor_id"],
        full_name=doc["full_name"],
        dob=doc.get("dob"),
        sex=doc.get("sex"),
        phone=doc.get("phone"),
        notes=doc.get("notes"),
        created_at=doc["created_at"],
        active_revision=doc.get("active_revision", 0),  # ✅ default 0 if missing
    )


@router.get("", response_model=list[PatientOut])
async def list_patients(doctor_id: str = Depends(get_current_user_id)):
    cur = patients_col.find({"doctor_id": doctor_id}).sort("created_at", -1)
    return [to_out(d) async for d in cur]


@router.post("", response_model=PatientOut)
async def create_patient(payload: PatientCreate, doctor_id: str = Depends(get_current_user_id)):
    doc = payload.model_dump()

    # ✅ Convert dob (date) -> datetime (Mongo compatible)
    doc["dob"] = date_to_datetime(doc.get("dob"))

    # ✅ active_revision starts at 0 (no revision yet)
    doc.update({
        "doctor_id": doctor_id,
        "created_at": datetime.utcnow(),
        "active_revision": 0,
        "updated_at": datetime.utcnow(),
    })

    res = await patients_col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return to_out(doc)


@router.put("/{patient_id}", response_model=PatientOut)
async def update_patient(patient_id: str, payload: PatientCreate, doctor_id: str = Depends(get_current_user_id)):
    oid = ObjectId(patient_id)
    found = await patients_col.find_one({"_id": oid, "doctor_id": doctor_id})
    if not found:
        raise HTTPException(status_code=404, detail="Not found")

    update_doc = payload.model_dump()
    update_doc["dob"] = date_to_datetime(update_doc.get("dob"))
    update_doc["updated_at"] = datetime.utcnow()

    # ⚠️ Do NOT change active_revision here (kept as-is)
    await patients_col.update_one(
        {"_id": oid, "doctor_id": doctor_id},
        {"$set": update_doc},
    )

    updated = await patients_col.find_one({"_id": oid})
    return to_out(updated)


@router.delete("/{patient_id}")
async def delete_patient(patient_id: str, doctor_id: str = Depends(get_current_user_id)):
    oid = ObjectId(patient_id)
    res = await patients_col.delete_one({"_id": oid, "doctor_id": doctor_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
