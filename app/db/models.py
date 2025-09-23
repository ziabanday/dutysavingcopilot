from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Text, Date, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.sql import func
from typing import Optional

class Base(DeclarativeBase):
    pass

# =========================
# Existing Week-1/2 models
# =========================

class HTSItem(Base):
    __tablename__ = "hts_items"
    # IMPORTANT for SQLite: use Integer (not BigInteger) for autoincrement PK
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str] = mapped_column(Text)
    duty_rate: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    chapter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class Ruling(Base):
    __tablename__ = "rulings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ruling_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    # JSON works on SQLite and Postgres; we can migrate to ARRAY later in Supabase
    hts_codes: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    ruling_date: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)
    chunks = relationship("RulingChunk", back_populates="ruling", cascade="all, delete-orphan")

class RulingChunk(Base):
    __tablename__ = "ruling_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ruling_id_fk: Mapped[int] = mapped_column(ForeignKey("rulings.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # store embeddings as JSON for dev; pgvector column when we move to Supabase
    embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    chunk_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    ruling = relationship("Ruling", back_populates="chunks")

# =========================
# New Week-3 models
# =========================

class SourceDocument(Base):
    """
    Canonical registry of ingested sources (HTS rows, rulings, etc.).
    Version increments on re-ingest; stable IDs are formed using this row.
    """
    __tablename__ = "source_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)   # "hts" | "ruling" | future types
    external_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., ruling_id or HTS code
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("source_type", "external_id", "version", name="uq_src_ver"),
    )

class Chunk(Base):
    """
    Normalized text chunks with stable IDs and optional embedding payloads.
    """
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # src:{source_id}:v{v}:p{page}:c{idx}
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0 for HTS
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)      # list[float] (dev)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)           # {section, heading, tokens, ...}
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())

    source = relationship("SourceDocument")

class IndexMeta(Base):
    """
    Audit rows for index builds (BM25, FAISS), useful for reproducibility.
    """
    __tablename__ = "index_meta"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)    # "bm25" | "faiss"
    version: Mapped[str] = mapped_column(String, nullable=False) # arbitrary tag like "dev" or git sha
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())

class Evidence(Base):
    """
    Captured snippet references attached to each /classify response for audit & eval.
    """
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    classify_call_id: Mapped[str] = mapped_column(String, nullable=False)  # request UUID
    suggested_code: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(String, nullable=False)
    passage: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)      # {score, url}
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())
