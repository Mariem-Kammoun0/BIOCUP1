import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

load_dotenv()

COLLECTION = "biocup_hybrid_splade_v1"

client = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ.get("QDRANT_API_KEY"),
)

indexes = [
    ("is_admin_noise", qm.PayloadSchemaType.INTEGER),
    ("section", qm.PayloadSchemaType.KEYWORD),
    ("primary_site", qm.PayloadSchemaType.KEYWORD),
    ("case_id", qm.PayloadSchemaType.KEYWORD),

    ("has_ihc", qm.PayloadSchemaType.BOOL),
    ("has_lymph", qm.PayloadSchemaType.BOOL),
    ("has_margins", qm.PayloadSchemaType.BOOL),
    ("has_tnm", qm.PayloadSchemaType.BOOL),
    ("has_size", qm.PayloadSchemaType.BOOL),
]

for field_name, schema in indexes:
    try:
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name=field_name,
            field_schema=schema
        )
        print("✅ created index:", field_name)
    except Exception as e:
        # souvent: already exists
        print("ℹ️ skip:", field_name, "-", str(e)[:120])
