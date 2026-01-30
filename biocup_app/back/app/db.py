from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings

client = AsyncIOMotorClient(settings.MONGO_URL)
db = client[settings.DB_NAME]

doctors_col = db["doctors"]
patients_col = db["patients"]
revisions_col = db["patient_revisions"]
results_col = db["patient_revision_results"]
