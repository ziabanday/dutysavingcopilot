
Usage (after your server is running or in a second terminal, with .venv active):

# 1) Initialize DB (sqlite fallback if DATABASE_URL not set)
python -c "from app.db.session import init_db; init_db()"

# 2) Load HTS (replace with your real file when ready)
python app/db/hts_parser.py data/hts/sample.json

# 3) Ingest a sample ruling (replace with real IDs later)
python app/db/cross_ingest.py --ids "NY N000000"
