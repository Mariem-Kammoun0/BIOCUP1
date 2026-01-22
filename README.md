
# BIOCUP — Semantic Chunking & Vector Retrieval Pipeline

BIOCUP is a research-oriented semantic chunking and vector retrieval project designed for structured biomedical documents.
It focuses on clean preprocessing, semantic chunking, embedding generation, and storage in a vector database for similarity search and RAG pipelines.

---
## 🚀 Quick Start (First Time Setup)

### macos
chmod +x setup.sh
./setup.sh

#### windows
./setup.ps1

#### create environment variables 
cp .env.example .env
#### check setup 
python -c "from backend.config.settings import QDRANT_URL; print(QDRANT_URL)"
#### install requirements
pip install -r requirements.txt
