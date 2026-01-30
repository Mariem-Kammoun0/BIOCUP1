from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, date


# =========================
# AUTH
# =========================
class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# =========================
# DOCTOR
# =========================
class DoctorRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    speciality: Optional[str] = None
    hospital: Optional[str] = None


class DoctorOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    speciality: Optional[str] = None
    hospital: Optional[str] = None


# =========================
# PATIENT
# =========================
class PatientCreate(BaseModel):
    full_name: str
    dob: Optional[date] = None
    sex: Optional[Literal["F", "M", "Other"]] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class PatientOut(BaseModel):
    id: str
    doctor_id: str
    full_name: str
    dob: Optional[date] = None
    sex: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    active_revision: Optional[int] = None  # keep if you still use revisions


# =========================
# REVISION FORM (INPUT)
# =========================
class PatientForm(BaseModel):
    """
    Structured input from UI.
    """
    histology: Optional[str] = None
    metastasis_sites: List[str] = Field(default_factory=list)
    lymph_nodes_summary: Optional[str] = None  # ex: "0/6 negative"
    tnm: Optional[str] = None                  # ex: "pT2N0M1"
    ihc: Dict[str, Optional[str]] = Field(default_factory=dict)  # {"CK7":"positive","TTF-1":"negative"}
    notes: Optional[str] = None


# =========================
# IMAGES (stored metadata)
# =========================
class ImageMeta(BaseModel):
    """
    Metadata saved in Mongo for each uploaded image.
    If you save to local disk, `relative_path` and/or `url` can be used by the UI.
    If you later switch to S3/GridFS, keep the same schema and just change `storage`.
    """
    image_id: str
    filename: str
    stored_filename: Optional[str] = None
    content_type: str
    size_bytes: int

    storage: str = "local"  # "local" | "s3" | "gridfs" ...
    relative_path: Optional[str] = None
    url: Optional[str] = None

    created_at: datetime


# =========================
# REVISION OUTPUTS
# =========================
class RevisionOut(BaseModel):
    """
    Light response for lists / quick acknowledgements.
    """
    patient_id: str
    revision: int
    index_status: str
    created_at: datetime


class RevisionDetail(BaseModel):
    """
    Full revision object returned by GET revision.
    Useful for UI to re-fill the form and show images/report/chunks.
    """
    id: str  # stringified Mongo _id
    patient_id: str
    doctor_id: str
    revision: int

    status: str
    created_at: datetime
    updated_at: datetime

    # All fields the doctor entered
    form_data: PatientForm

    # Generated report & chunks
    generated_report_text: str
    chunks: List[Dict[str, Any]] = Field(default_factory=list)

    # Images metadata
    images: List[ImageMeta] = Field(default_factory=list)

    # Indexing / errors
    index_status: str = "not_indexed"
    error: Optional[str] = None


# =========================
# OPTIONAL: "single revision per patient" mode
# =========================
class SingleRevisionOut(BaseModel):
    """
    Use this if you decide to keep ONLY ONE revision per patient (updatable),
    and you don't want to expose revision numbers.
    """
    patient_id: str
    index_status: str
    created_at: datetime
    updated_at: datetime


class SingleRevisionDetail(BaseModel):
    """
    Full object for the single-revision strategy.
    """
    id: str
    patient_id: str
    doctor_id: str

    status: str
    created_at: datetime
    updated_at: datetime

    form_data: PatientForm
    generated_report_text: str
    chunks: List[Dict[str, Any]] = Field(default_factory=list)
    images: List[ImageMeta] = Field(default_factory=list)

    index_status: str = "not_indexed"
    error: Optional[str] = None
