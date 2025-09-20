from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Text, Date, ForeignKey, JSON
from typing import Optional

class Base(DeclarativeBase):
    pass

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
