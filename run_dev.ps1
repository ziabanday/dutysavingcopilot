\
# Windows PowerShell convenience script
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app/db/seed_sample.py
uvicorn app.api.main:app --reload
