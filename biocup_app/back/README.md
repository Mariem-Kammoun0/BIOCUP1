# etapes a executer pour le setup backend

cd backend
python -m venv .venv
# windows:
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
