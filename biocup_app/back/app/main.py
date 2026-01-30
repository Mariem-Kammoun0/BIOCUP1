from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.routes_auth import router as auth_router
from .routes.routes_patients import router as patients_router
from .routes.routes_submit import router as submit_router

from .routes.routes_results import router as results_router
...

app = FastAPI(title="BioCUP Doctors & Patients API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "message": "API is running"}

app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(submit_router)
app.include_router(results_router)