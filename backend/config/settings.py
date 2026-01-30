from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL","openclip:ViT-B-32/laion2b_s34b_b79k")

if not all([QDRANT_URL]):
    raise RuntimeError("❌ Missing environment variables. Check your .env file.")

# Project root (important)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

CSV_PATH = PROJECT_ROOT / "data" / "images" / "ihc.csv"
IMAGES_ROOT = PROJECT_ROOT
BATCH_SIZE = 32

# canonical cancers
CANON_CANCER = {
    "lungs": "lung",
    "lung": "lung",
    "breast": "breast",
    "colon": "colon",
    "pancreas": "pancreas",
    "liver": "liver",
    "ovary": "ovary",
    "prostate": "prostate",
}