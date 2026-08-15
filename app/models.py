from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    # Fetch server-generated column values (now()/onupdate) via RETURNING at
    # flush time. Prevents expired attributes that would trigger an async
    # lazy-refresh (MissingGreenlet) when API routes return ORM objects.
    __mapper_args__ = {"eager_defaults": True}


class FieldType(str, enum.Enum):
    PROVED = "PROVED"
    INFERRED = "INFERRED"
    HUMAN = "HUMAN"
    UNKNOWN = "UNKNOWN"
    DISPUTE = "DISPUTE"


class ProductStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    REVIEW = "review"
    EXPORTED = "exported"
    FAILED = "failed"


class BatchStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), index=True)
    source_filename: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    part_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[ProductStatus] = mapped_column(Enum(ProductStatus), nullable=False, default=ProductStatus.PENDING, index=True)
    confidence_distribution: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ponytail: selectin eager-loads fields together with Product — avoids sync lazy-load
    # inside async session (MissingGreenlet). Swap to lazy="raise" + explicit options() if N+1 matters.
    fields: Mapped[list["ProductField"]] = relationship("ProductField", back_populates="product", cascade="all, delete-orphan", lazy="selectin")


class ProductField(Base):
    __tablename__ = "product_fields"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    attribute_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attribute_label: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # ponytail: String (not native Enum) to match init.sql Text column; avoids
    # Postgres enum-type mismatch on filter comparisons. Python FieldType validates writes.
    field_type: Mapped[FieldType] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    extraction_strength: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_authority: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    agreement: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sources: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    reason_chain: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    physical_constraints: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    constraint_violation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # ponytail: String (not native Enum) so it matches the Text column in init.sql
    # and avoids Postgres enum-type mismatch. Python ReviewStatus enum still validates writes.
    review_status: Mapped[ReviewStatus] = mapped_column(String(32), nullable=False, default=ReviewStatus.PENDING, index=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    product: Mapped["Product"] = relationship("Product", back_populates="fields")


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    total_products: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_products: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[BatchStatus] = mapped_column(Enum(BatchStatus), nullable=False, default=BatchStatus.QUEUED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SKURelationship(Base):
    __tablename__ = "sku_relationships"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku_a: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sku_b: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    attributes_shared: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("sku_a", "sku_b", "relationship_type", name="uq_sku_relationship"),)


class FieldAudit(Base):
    __tablename__ = "field_audit"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    field_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("product_fields.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    old_value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Cross-reference RAG is post-MVP; keep embeddings as plain JSON so the schema
    # works on stock Postgres without the pgvector extension. Swap to Vector(1024)
    # when the vector store ships.
    embedding: Mapped[Optional[list[float]]] = mapped_column(JSON, nullable=True)
    chunk_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Pydantic schemas for API ---

class SourceRef(BaseModel):
    ref: str
    authority: float
    agreement: str
    bbox: Optional[list[float]] = None


class ProductFieldCreate(BaseModel):
    attribute_key: str
    attribute_label: Optional[str] = None
    value: Optional[str] = None
    unit: Optional[str] = None
    field_type: FieldType
    confidence: float = Field(ge=0, le=1)
    extraction_strength: Optional[float] = Field(default=None, ge=0, le=1)
    source_authority: Optional[float] = Field(default=None, ge=0, le=1)
    agreement: Optional[float] = Field(default=None, ge=0, le=1)
    sources: list[SourceRef] = Field(default_factory=list)
    reason_chain: list[str] = Field(default_factory=list)
    physical_constraints: Optional[dict] = None
    constraint_violation: bool = False


class ProductFieldRead(ProductFieldCreate):
    id: uuid.UUID
    product_id: uuid.UUID
    review_status: ReviewStatus
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    batch_id: Optional[uuid.UUID] = None
    source_filename: str
    source_hash: str
    source_type: str
    part_number: Optional[str] = None
    manufacturer: Optional[str] = None
    category: Optional[str] = None


class ProductRead(BaseModel):
    id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
    source_filename: str
    source_hash: str
    source_type: str
    part_number: Optional[str] = None
    manufacturer: Optional[str] = None
    category: Optional[str] = None
    status: ProductStatus
    confidence_distribution: dict
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    fields: list[ProductFieldRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class BatchCreate(BaseModel):
    name: str


class BatchRead(BaseModel):
    id: uuid.UUID
    name: str
    total_products: int
    processed_products: int
    status: BatchStatus
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SKURelationshipCreate(BaseModel):
    sku_a: str
    sku_b: str
    relationship_type: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    attributes_shared: Optional[list[str]] = None
    source: Optional[str] = None


class SKURelationshipRead(SKURelationshipCreate):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True