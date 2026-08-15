-- PASTE database schema
-- Native enum types match SQLAlchemy's Enum(...) columns so app + init.sql
-- agree on column types (avoids `text = reviewstatus` mismatches).

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'productstatus') THEN
        CREATE TYPE productstatus AS ENUM ('PENDING','PROCESSING','REVIEW','EXPORTED','FAILED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'fieldtype') THEN
        CREATE TYPE fieldtype AS ENUM ('PROVED','INFERRED','HUMAN','UNKNOWN','DISPUTE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reviewstatus') THEN
        CREATE TYPE reviewstatus AS ENUM ('PENDING','ACCEPTED','REJECTED','EDITED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'batchstatus') THEN
        CREATE TYPE batchstatus AS ENUM ('QUEUED','PROCESSING','REVIEW','COMPLETED','FAILED');
    END IF;
END$$;

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id UUID,
    source_filename TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    source_type TEXT NOT NULL,
    part_number TEXT,
    manufacturer TEXT,
    category TEXT,
    status productstatus NOT NULL DEFAULT 'PENDING',
    confidence_distribution JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_products_batch ON products(batch_id);
CREATE INDEX idx_products_status ON products(status);
CREATE UNIQUE INDEX idx_products_source_hash ON products(source_hash);

CREATE TABLE product_fields (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    attribute_key TEXT NOT NULL,
    attribute_label TEXT,
    value TEXT,
    unit TEXT,
    field_type fieldtype NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    extraction_strength REAL,
    source_authority REAL,
    agreement REAL,
    sources JSONB NOT NULL DEFAULT '[]',
    reason_chain JSONB NOT NULL DEFAULT '[]',
    physical_constraints JSONB,
    constraint_violation BOOLEAN DEFAULT FALSE,
    review_status reviewstatus DEFAULT 'PENDING',
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_product_fields_product ON product_fields(product_id);
CREATE INDEX idx_product_fields_type ON product_fields(field_type);
CREATE INDEX idx_product_fields_review ON product_fields(review_status);

CREATE TABLE batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    total_products INTEGER NOT NULL DEFAULT 0,
    processed_products INTEGER NOT NULL DEFAULT 0,
    status batchstatus NOT NULL DEFAULT 'QUEUED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE sku_relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku_a TEXT NOT NULL,
    sku_b TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    attributes_shared JSONB,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sku_rel_a ON sku_relationships(sku_a);
CREATE INDEX idx_sku_rel_b ON sku_relationships(sku_b);

CREATE TABLE field_audit (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v1mc() NULL,
    field_id UUID NOT NULL REFERENCES product_fields(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB,
    actor TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_field_audit_field ON field_audit(field_id);

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type TEXT NOT NULL,
    source_url TEXT,
    content TEXT NOT NULL,
    embedding JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
