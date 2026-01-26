# BIOCUP – Biomedical Case Understanding Platform

BIOCUP is a **semantic retrieval and clinical memory system** designed to support **Cancer of Unknown Primary (CUP)** diagnosis.  
It transforms unstructured pathology reports into **clinically coherent chunks**, encodes them as **dense and sparse embeddings**, and enables **similarity-based retrieval** using **Qdrant**.

BIOCUP is **not a chatbot**.  
It is a backend system for **clinical reasoning by analogy** over resolved cancer cases.

---

## 🎯 Problem Addressed

In Cancer of Unknown Primary (CUP), metastatic cancer is identified but the **primary tumor site remains unknown**.  
Although pathology reports contain crucial diagnostic clues (IHC markers, lymph node patterns, TNM staging), these clues are buried in long, unstructured clinical text.

BIOCUP enables:
- Structuring pathology reports into **clinically meaningful units**
- Semantic similarity search across resolved cancer cases
- Hybrid retrieval combining **embeddings + clinical filters**

---

## 🏗️ High-Level Architecture

Raw Pathology Reports
↓
Preprocessing & Normalization
↓
Clinically Aware Semantic Chunking
↓
Clinical Feature Extraction
↓
Dense + Sparse Embeddings
↓
Qdrant Vector Database
↓
Similarity Search & Case Aggregation

---

## ✂️ Clinically Aware Semantic Chunking

Pathology reports are segmented into **medical sections**, ensuring that each chunk represents a coherent diagnostic concept.

Typical chunk categories:
- SPECIMEN
- DIAGNOSIS
- LYMPH NODES
- MARGINS
- IMMUNOHISTOCHEMISTRY (IHC)
- SYNOPTIC REPORT

Each chunk is treated as an **independent retrieval unit**.

---

## 🧠 Embeddings (Dense + Sparse)

Each semantic chunk is represented by **two complementary embeddings**:

- **Dense embeddings** (transformer-based): capture semantic meaning and context  
- **Sparse embeddings** (term-based): emphasize exact diagnostic markers (e.g. IHC stains, TNM tokens)

This hybrid representation is particularly effective for CUP, where **partial matches and rare markers** are diagnostically important.

---

## 📦 Vector Database: Qdrant

BIOCUP uses **Qdrant** as its vector database and semantic memory.

Each stored vector includes:
- Vector embedding (dense and/or sparse)
- Payload metadata:
  - `case_id`
  - `patient_id`
  - `primary_site` (known for reference cases)
  - `cancer_type`, `cancer_subtype`
  - `section` (DIAGNOSIS, IHC, etc.)
  - Clinical flags (`has_ihc`, `has_lymph`, `has_tnm`, `has_size`, `has_margins`)

This enables **hybrid semantic + clinical filtering** during search.

---

## 📁 Project Structure

BIOCUP/
├── backend/
│ ├── chunking/ # Clinically aware semantic chunking logic
│ ├── config/ # Configuration files (Qdrant, settings)
│ ├── embedding/ # Dense and sparse embedding generation
│ ├── indexing/ # Qdrant collection creation & vector indexing
│ ├── search/ # Similarity search and retrieval logic
│ └── biocup_chunks_stats.json
│
├── data/
│ ├── input/ # Input pathology reports
│ ├── raw/ # Original raw data
│ ├── processed/ # Chunked & cleaned outputs
│ └── embeddings/ # Saved embeddings (optional)
│
├── notebooks/ # Exploration and experiments
├── .env # Environment variables (local)
├── .env.example # Environment variable template
├── .gitignore
├── requirements.txt
├── setup.sh # Linux / macOS setup script
├── setup.ps1 # Windows PowerShell setup script
└── README.md


---

## ✂️ Clinically Aware Semantic Chunking

BIOCUP segments pathology reports into **medical sections**, ensuring that each chunk represents a coherent diagnostic concept.

Typical chunk categories:
- SPECIMEN
- DIAGNOSIS
- LYMPH NODES
- MARGINS
- IMMUNOHISTOCHEMISTRY (IHC)
- SYNOPTIC REPORT

Each chunk is treated as an **independent retrieval unit**, preventing dilution of diagnostic signals.

---

## 🧠 Embeddings (Dense + Sparse)

Each semantic chunk is represented by **two complementary vectors**:

- **Dense embeddings** (transformer-based): capture semantic and contextual meaning
- **Sparse embeddings** (term-based): emphasize exact diagnostic markers (e.g., IHC stains, TNM tokens)

This hybrid representation is particularly effective for CUP, where both semantic similarity and exact marker matching are critical.

---

## 📦 Vector Database: Qdrant

BIOCUP uses **Qdrant** as its vector database and semantic memory.

Each stored vector includes:
- Vector embedding (dense and/or sparse)
- Payload metadata:
  - `case_id`
  - `patient_id`
  - `primary_site` (known for reference cases)
  - `cancer_type`, `cancer_subtype`
  - `section` (DIAGNOSIS, IHC, etc.)
  - Clinical flags (`has_ihc`, `has_lymph`, `has_tnm`, `has_size`, `has_margins`)

This enables **hybrid semantic + clinical filtering** during retrieval.

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

