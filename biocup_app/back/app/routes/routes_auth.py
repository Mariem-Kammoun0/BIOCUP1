from fastapi import APIRouter, HTTPException, Depends
from ..db import doctors_col, patients_col, revisions_col
from ..models import DoctorRegister, RevisionOut
from bson import ObjectId
from ..auth import hash_password, verify_password, create_access_token
from ..auth import get_current_user_id

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register")
async def register(doctor: DoctorRegister):
    existing = await doctors_col.find_one({"email": doctor.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already used")

    doc = {
        "email": doctor.email,
        "password_hash": hash_password(doctor.password),
        "full_name": doctor.full_name,
        "speciality": doctor.speciality,
        "hospital": doctor.hospital,
        "role": "doctor"
    }

    res = await doctors_col.insert_one(doc)
    return {"id": str(res.inserted_id), "email": doctor.email}

@router.post("/login")
async def login(payload: DoctorRegister):
    db_doc = await doctors_col.find_one({"email": payload.email})
    if not db_doc or not verify_password(payload.password, db_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Bad credentials")

    token = create_access_token(str(db_doc["_id"]))
    return {"access_token": token, "token_type": "bearer"}

@router.get("/{patient_id}/revisions", response_model=list[RevisionOut])
async def list_revisions(patient_id: str, doctor_id: str = Depends(get_current_user_id)):
    # check ownership
    patient = await patients_col.find_one({"_id": ObjectId(patient_id), "doctor_id": doctor_id})
    if not patient:
        raise HTTPException(404, "Patient not found")

    cur = revisions_col.find({"patient_id": patient_id, "doctor_id": doctor_id}).sort("revision", -1)
    out = []
    async for d in cur:
        out.append(RevisionOut(
            patient_id=d["patient_id"],
            revision=d["revision"],
            index_status=d.get("index_status", "pending"),
            created_at=d["created_at"],
        ))
    return out
