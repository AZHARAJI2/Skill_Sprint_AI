"""SQLAlchemy models for ingested documents, chunks, and version history."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from database.base import Base


class Document(Base):
    """One uploaded file of a company document (a document_id may have multiple files/versions)."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("file_hash", name="uq_documents_file_hash"),
        UniqueConstraint("document_id", "version", "file_type", name="uq_documents_id_ver_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))
    version: Mapped[str] = mapped_column(String(32), default="v1")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_path: Mapped[str] = mapped_column(String(512))
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    """Parsed section-level chunk with full source traceability metadata."""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_pk: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    section_id: Mapped[str] = mapped_column(String(32), index=True)
    heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    is_role_specific: Mapped[bool] = mapped_column(Boolean, default=False)
    flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    embedding_vector: Mapped[list | None] = mapped_column(JSON, nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")


class DocumentRevision(Base):
    """Logical version of a document_id (active vs obsolete), independent of file format."""

    __tablename__ = "document_revisions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_revision_doc_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="active")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
