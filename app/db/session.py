
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base
from app.utils.logging_setup import get_logger

log = get_logger("db")

def get_database_url():
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # offline dev fallback to sqlite (so you can run without Postgres)
    return "sqlite:///local.db"

engine = create_engine(get_database_url(), echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def init_db():
    Base.metadata.create_all(bind=engine)
    log.info("DB initialized at %s", get_database_url())
