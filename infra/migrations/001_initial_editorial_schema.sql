BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS operational;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS operational.ingestion_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL CHECK (btrim(source) <> ''),
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('scheduled', 'manual', 'reprocess')),
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'partial_failure', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count > 0),
    items_discovered INTEGER NOT NULL DEFAULT 0 CHECK (items_discovered >= 0),
    items_created INTEGER NOT NULL DEFAULT 0 CHECK (items_created >= 0),
    items_deduplicated INTEGER NOT NULL DEFAULT 0 CHECK (items_deduplicated >= 0),
    error_detail TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (
        (status = 'running' AND finished_at IS NULL)
        OR (status <> 'running' AND finished_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS operational.object_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES operational.ingestion_runs(id) ON DELETE RESTRICT,
    source TEXT NOT NULL CHECK (btrim(source) <> ''),
    source_id TEXT NOT NULL CHECK (btrim(source_id) <> ''),
    bucket_name TEXT NOT NULL CHECK (btrim(bucket_name) <> ''),
    object_key TEXT NOT NULL CHECK (btrim(object_key) <> ''),
    content_hash TEXT,
    content_size_bytes BIGINT,
    status TEXT NOT NULL CHECK (status IN ('pending_upload', 'uploaded', 'verified', 'linked', 'failed')),
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_at TIMESTAMPTZ,
    UNIQUE (source, source_id),
    UNIQUE (bucket_name, object_key),
    CHECK (content_size_bytes IS NULL OR content_size_bytes >= 0),
    CHECK (content_hash IS NULL OR content_hash ~ '^[A-Fa-f0-9]{64}$'),
    CHECK (
        status NOT IN ('verified', 'linked')
        OR verified_at IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS bronze.articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES operational.ingestion_runs(id) ON DELETE RESTRICT,
    object_receipt_id UUID NOT NULL REFERENCES operational.object_receipts(id) ON DELETE RESTRICT,
    source TEXT NOT NULL CHECK (btrim(source) <> ''),
    source_id TEXT NOT NULL CHECK (btrim(source_id) <> ''),
    headline TEXT NOT NULL CHECK (btrim(headline) <> ''),
    author_name TEXT,
    source_url TEXT NOT NULL CHECK (btrim(source_url) <> ''),
    download_url TEXT NOT NULL CHECK (btrim(download_url) <> ''),
    source_category TEXT,
    source_content_date DATE,
    source_included_at TIMESTAMPTZ,
    bucket_name TEXT NOT NULL CHECK (btrim(bucket_name) <> ''),
    object_key TEXT NOT NULL CHECK (btrim(object_key) <> ''),
    content_hash TEXT NOT NULL CHECK (content_hash ~ '^[A-Fa-f0-9]{64}$'),
    content_size_bytes BIGINT NOT NULL CHECK (content_size_bytes >= 0),
    raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, source_id),
    UNIQUE (bucket_name, object_key)
);

CREATE TABLE IF NOT EXISTS silver.articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bronze_article_id UUID NOT NULL UNIQUE REFERENCES bronze.articles(id) ON DELETE RESTRICT,
    headline TEXT NOT NULL CHECK (btrim(headline) <> ''),
    author_name TEXT,
    category TEXT,
    source_content_date DATE,
    review_status TEXT NOT NULL DEFAULT 'captured'
        CHECK (review_status IN ('captured', 'in_review', 'approved', 'rejected')),
    normalization_version INTEGER NOT NULL DEFAULT 1 CHECK (normalization_version > 0),
    normalized_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gold.articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    silver_article_id UUID NOT NULL REFERENCES silver.articles(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL CHECK (version > 0),
    source TEXT NOT NULL CHECK (btrim(source) <> ''),
    source_id TEXT NOT NULL CHECK (btrim(source_id) <> ''),
    headline TEXT NOT NULL CHECK (btrim(headline) <> ''),
    author_name TEXT NOT NULL CHECK (btrim(author_name) <> ''),
    source_url TEXT NOT NULL CHECK (btrim(source_url) <> ''),
    bucket_name TEXT NOT NULL CHECK (btrim(bucket_name) <> ''),
    object_key TEXT NOT NULL CHECK (btrim(object_key) <> ''),
    content_hash TEXT NOT NULL CHECK (content_hash ~ '^[A-Fa-f0-9]{64}$'),
    content_size_bytes BIGINT NOT NULL CHECK (content_size_bytes >= 0),
    approved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by TEXT,
    snapshot_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (silver_article_id, version),
    UNIQUE (bucket_name, object_key)
);

CREATE TABLE IF NOT EXISTS operational.audit_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID REFERENCES operational.ingestion_runs(id) ON DELETE SET NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('object_receipt', 'bronze_article', 'silver_article', 'gold_article')),
    entity_id UUID NOT NULL,
    event_type TEXT NOT NULL CHECK (btrim(event_type) <> ''),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ingestion_runs_source_started_at_idx
    ON operational.ingestion_runs (source, started_at DESC);
CREATE INDEX IF NOT EXISTS object_receipts_reconciliation_idx
    ON operational.object_receipts (status, created_at)
    WHERE status IN ('pending_upload', 'uploaded', 'failed');
CREATE INDEX IF NOT EXISTS bronze_articles_source_date_idx
    ON bronze.articles (source, source_content_date DESC, captured_at DESC);
CREATE INDEX IF NOT EXISTS bronze_articles_raw_metadata_gin_idx
    ON bronze.articles USING GIN (raw_metadata);
CREATE INDEX IF NOT EXISTS silver_articles_review_idx
    ON silver.articles (review_status, created_at DESC);
CREATE INDEX IF NOT EXISTS silver_articles_metadata_gin_idx
    ON silver.articles USING GIN (normalized_metadata);
CREATE INDEX IF NOT EXISTS gold_articles_source_idx
    ON gold.articles (source, source_id, approved_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_entity_idx
    ON operational.audit_events (entity_type, entity_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION operational.require_verified_object_receipt()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM operational.object_receipts receipt
        WHERE receipt.id = NEW.object_receipt_id
          AND receipt.run_id = NEW.run_id
          AND receipt.source = NEW.source
          AND receipt.source_id = NEW.source_id
          AND receipt.bucket_name = NEW.bucket_name
          AND receipt.object_key = NEW.object_key
          AND receipt.content_hash = NEW.content_hash
          AND receipt.content_size_bytes = NEW.content_size_bytes
          AND receipt.status IN ('verified', 'linked')
    ) THEN
        RAISE EXCEPTION 'Bronze exige objeto MinIO verificado e compatível com a captura';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION bronze.prevent_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Bronze é imutável; crie uma nova camada Silver ou Gold';
END;
$$;

CREATE OR REPLACE FUNCTION gold.prevent_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Gold é um snapshot imutável; crie uma nova versão';
END;
$$;

CREATE OR REPLACE FUNCTION operational.touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS bronze_require_verified_object_trigger ON bronze.articles;
CREATE TRIGGER bronze_require_verified_object_trigger
    BEFORE INSERT ON bronze.articles
    FOR EACH ROW EXECUTE FUNCTION operational.require_verified_object_receipt();

DROP TRIGGER IF EXISTS bronze_immutable_trigger ON bronze.articles;
CREATE TRIGGER bronze_immutable_trigger
    BEFORE UPDATE OR DELETE ON bronze.articles
    FOR EACH ROW EXECUTE FUNCTION bronze.prevent_mutation();

DROP TRIGGER IF EXISTS silver_touch_updated_at_trigger ON silver.articles;
CREATE TRIGGER silver_touch_updated_at_trigger
    BEFORE UPDATE ON silver.articles
    FOR EACH ROW EXECUTE FUNCTION operational.touch_updated_at();

DROP TRIGGER IF EXISTS gold_immutable_trigger ON gold.articles;
CREATE TRIGGER gold_immutable_trigger
    BEFORE UPDATE OR DELETE ON gold.articles
    FOR EACH ROW EXECUTE FUNCTION gold.prevent_mutation();

COMMIT;
