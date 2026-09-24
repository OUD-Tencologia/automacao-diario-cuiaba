BEGIN;

-- A migration 001 pertence ao contrato técnico anterior. Como ela nunca foi
-- aplicada na homologação real, a transição só é permitida se as estruturas
-- legadas estiverem vazias. Nunca removemos conteúdo editorial existente.
DO $$
DECLARE
    table_name TEXT;
    has_rows BOOLEAN;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'operational.ingestion_runs',
        'operational.object_receipts',
        'operational.audit_events',
        'bronze.articles',
        'silver.articles',
        'gold.articles'
    ]
    LOOP
        IF to_regclass(table_name) IS NOT NULL THEN
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %s)', table_name)
            INTO has_rows;

            IF has_rows THEN
                RAISE EXCEPTION
                    'A transição para a Gold única foi bloqueada: % contém dados',
                    table_name;
            END IF;
        END IF;
    END LOOP;
END;
$$;

-- Somente objetos criados pela migration legada são removidos. DROP SCHEMA
-- sem CASCADE falha em vez de remover artefatos estranhos ao projeto.
DROP TABLE IF EXISTS operational.audit_events;
DROP TABLE IF EXISTS gold.articles;
DROP TABLE IF EXISTS silver.articles;
DROP TABLE IF EXISTS bronze.articles;
DROP TABLE IF EXISTS operational.object_receipts;
DROP TABLE IF EXISTS operational.ingestion_runs;

DROP FUNCTION IF EXISTS operational.require_verified_object_receipt();
DROP FUNCTION IF EXISTS bronze.prevent_mutation();
DROP FUNCTION IF EXISTS gold.prevent_mutation();
DROP FUNCTION IF EXISTS operational.touch_updated_at();

DROP SCHEMA IF EXISTS operational;
DROP SCHEMA IF EXISTS bronze;
DROP SCHEMA IF EXISTS silver;
DROP SCHEMA IF EXISTS gold;

CREATE SCHEMA gold;

CREATE TABLE gold.articles (
    source TEXT NOT NULL CHECK (btrim(source) <> ''),
    id TEXT NOT NULL CHECK (btrim(id) <> ''),
    dt_noticia TIMESTAMPTZ NOT NULL,
    ds_chapeu TEXT,
    ds_titulo TEXT NOT NULL CHECK (btrim(ds_titulo) <> ''),
    nm_autor TEXT,
    ds_local TEXT,
    ds_noticia TEXT NOT NULL CHECK (btrim(ds_noticia) <> ''),
    ds_resumo TEXT CHECK (ds_resumo IS NULL OR char_length(ds_resumo) <= 150),
    destaque BOOLEAN NOT NULL DEFAULT FALSE,
    tipo_de_conteudo TEXT NOT NULL DEFAULT 'INTERNO'
        CHECK (tipo_de_conteudo IN ('PUBLICO', 'INTERNO')),
    publicar_imediatamente BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'FILA_EDITORIAL'
        CHECK (status IN (
            'FILA_EDITORIAL', 'EM_EDICAO', 'REVISAO', 'APROVADO',
            'DESCARTADO', 'PUBLICADO'
        )),
    source_url TEXT NOT NULL CHECK (btrim(source_url) <> ''),
    minio_bucket TEXT NOT NULL CHECK (btrim(minio_bucket) <> ''),
    minio_object_key TEXT NOT NULL CHECK (btrim(minio_object_key) <> ''),
    raw_sha256 TEXT NOT NULL CHECK (raw_sha256 ~ '^[A-Fa-f0-9]{64}$'),
    raw_size_bytes BIGINT NOT NULL CHECK (raw_size_bytes >= 0),
    raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, id),
    UNIQUE (minio_bucket, minio_object_key)
);

CREATE INDEX gold_articles_queue_idx
    ON gold.articles (status, dt_noticia DESC, created_at DESC);
CREATE INDEX gold_articles_source_date_idx
    ON gold.articles (source, dt_noticia DESC);
CREATE INDEX gold_articles_metadata_gin_idx
    ON gold.articles USING GIN (raw_metadata);

CREATE FUNCTION gold.touch_update_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.update_at = now();
    RETURN NEW;
END;
$$;

CREATE FUNCTION gold.prevent_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Notícias Gold não podem ser apagadas; use STATUS=DESCARTADO';
END;
$$;

CREATE TRIGGER gold_articles_touch_update_at_trigger
    BEFORE UPDATE ON gold.articles
    FOR EACH ROW EXECUTE FUNCTION gold.touch_update_at();

CREATE TRIGGER gold_articles_prevent_delete_trigger
    BEFORE DELETE ON gold.articles
    FOR EACH ROW EXECUTE FUNCTION gold.prevent_delete();

COMMIT;
