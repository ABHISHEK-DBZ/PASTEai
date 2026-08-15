-- PASTE database schema
-- Core trust model: every field carries type + confidence + provenance
--
-- Runs on stock PostgreSQL (no pgvector required). The web cross-reference RAG
-- (document_chunks.embedding) is post-MVP, so embeddings are stored as JSONB;
-- switch to VECTOR(n) + an HNSW index when the vector store ships.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Products (one per input document/batch item)
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id UUID,
    source_filename TEXT NOT NULL,
    source_hash TEXT NOT NULL,           -- content hash for idempotency
    source_type TEXT NOT NULL,           -- 'pdf' | 'image' | 'part_number' | 'url'
    part_number TEXT,
    manufacturer TEXT,
    category TEXT,                       -- ETIM/eCl@ss code
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | review | exported | failed
    confidence_distribution JSONB,       -- {auto_approve: 12, borderline: 3, forced_review: 1}
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_products_batch ON products(batch_id);
CREATE INDEX idx_products_status ON products(status);
CREATE UNIQUE INDEX idx_products_source_hash ON products(source_hash);

-- Product fields (one row per attribute per product)
CREATE TABLE product_fields (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    attribute_key TEXT NOT NULL,         -- e.g., 'voltage_rating', 'ip_rating'
    attribute_label TEXT,                -- human-readable
    value TEXT,                          -- extracted/normalized value
    unit TEXT,
    field_type TEXT NOT NULL,            -- PROVED | INFERRED | HUMAN | UNKNOWN | DISPUTE
    confidence REAL NOT NULL DEFAULT 0,
    extraction_strength REAL,            -- 1.0 | 0.8 | 0.5 | 0.4
    source_authority REAL,               -- 1.0 | 0.7 | 0.5 | 0.3
    agreement REAL,                      -- 1.0 | 0.7
    sources JSONB NOT NULL DEFAULT '[]', -- [{ref, authority, agreement, bbox}]
    reason_chain JSONB NOT NULL DEFAULT '[]',
    physical_constraints JSONB,          -- {min, max, enum_values, unit}
    constraint_violation BOOLEAN DEFAULT FALSE,
    review_status TEXT DEFAULT 'pending', -- pending | accepted | rejected | edited
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_product_fields_product ON product_fields(product_id);
CREATE INDEX idx_product_fields_type ON product_fields(field_type);
CREATE INDEX idx_product_fields_review ON product_fields(review_status);

-- Batches (group of products processed together)
CREATE TABLE batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    total_products INTEGER NOT NULL DEFAULT 0,
    processed_products INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'queued', -- queued | processing | review | completed | failed
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Knowledge graph: sibling SKU relationships for inference
CREATE TABLE sku_relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku_a TEXT NOT NULL,
    sku_b TEXT NOT NULL,
    relationship_type TEXT NOT NULL,     -- 'variant' | 'series' | 'compatible' | 'replacement'
    confidence REAL NOT NULL DEFAULT 1.0,
    attributes_shared JSONB,             -- which attributes are known shared
    source TEXT,                         -- 'catalog' | 'manual' | 'inferred'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sku_rel_a ON sku_relationships(sku_a);
CREATE INDEX idx_sku_rel_b ON sku_relationships(sku_b);

-- Audit trail for every field change
CREATE TABLE field_audit (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    field_id UUID NOT NULL REFERENCES product_fields(id) ON DELETE CASCADE,
    action TEXT NOT NULL,                -- created | updated | reviewed | exported
    old_value JSONB,
    new_value JSONB,
    actor TEXT,                          -- 'system' | 'user:<id>' | 'vlm'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_field_audit_field ON field_audit(field_id);

-- Document chunks for web cross-reference RAG (future)
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type TEXT NOT NULL,           -- 'manufacturer_web' | 'standard' | 'manual'
    source_url TEXT,
    content TEXT NOT NULL,
    embedding JSONB,                     -- embedding as JSONB until the vector store ships
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);