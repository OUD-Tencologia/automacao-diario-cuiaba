-- Executado somente em banco PostgreSQL descartável após a migration 001.
-- Não contém conteúdo ou credenciais licenciados da Folhapress.
DO $$
DECLARE
    v_ingestion_run_id UUID;
    v_receipt_id UUID;
    v_bronze_article_id UUID;
    v_silver_article_id UUID;
    v_gold_article_id UUID;
BEGIN
    INSERT INTO operational.ingestion_runs (
        source, trigger_type, status, finished_at
    ) VALUES (
        'folhapress', 'manual', 'succeeded', now()
    ) RETURNING id INTO v_ingestion_run_id;

    INSERT INTO operational.object_receipts (
        run_id, source, source_id, bucket_name, object_key, content_hash,
        content_size_bytes, status
    ) VALUES (
        v_ingestion_run_id, 'folhapress', '9990001', 'bronze-raw',
        'folhapress/2026/09/23/9990001.txt', repeat('a', 64), 512, 'uploaded'
    ) RETURNING id INTO v_receipt_id;

    BEGIN
        INSERT INTO bronze.articles (
            run_id, object_receipt_id, source, source_id, headline, author_name,
            source_url, download_url, bucket_name, object_key, content_hash,
            content_size_bytes
        ) VALUES (
            v_ingestion_run_id, v_receipt_id, 'folhapress', '9990001',
            'Matéria sintética para validação', 'Autora Sintética',
            'https://folhapress.example/texto/9990001',
            'https://folhapress.example/texto/9990001/baixar', 'bronze-raw',
            'folhapress/2026/09/23/9990001.txt', repeat('a', 64), 512
        );
        RAISE EXCEPTION 'O trigger de objeto verificado deveria ter rejeitado o Bronze';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM NOT LIKE 'Bronze exige objeto MinIO verificado%' THEN
            RAISE;
        END IF;
    END;

    UPDATE operational.object_receipts
    SET status = 'verified', verified_at = now()
    WHERE id = v_receipt_id;

    INSERT INTO bronze.articles (
        run_id, object_receipt_id, source, source_id, headline, author_name,
        source_url, download_url, bucket_name, object_key, content_hash,
        content_size_bytes
    ) VALUES (
        v_ingestion_run_id, v_receipt_id, 'folhapress', '9990001',
        'Matéria sintética para validação', 'Autora Sintética',
        'https://folhapress.example/texto/9990001',
        'https://folhapress.example/texto/9990001/baixar', 'bronze-raw',
        'folhapress/2026/09/23/9990001.txt', repeat('a', 64), 512
    ) RETURNING id INTO v_bronze_article_id;

    BEGIN
        UPDATE bronze.articles SET headline = 'Não permitido' WHERE id = v_bronze_article_id;
        RAISE EXCEPTION 'O trigger de imutabilidade do Bronze deveria ter rejeitado a alteração';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM NOT LIKE 'Bronze é imutável%' THEN
            RAISE;
        END IF;
    END;

    INSERT INTO silver.articles (bronze_article_id, headline, author_name)
    VALUES (v_bronze_article_id, 'Matéria sintética para validação', 'Autora Sintética')
    RETURNING id INTO v_silver_article_id;

    BEGIN
        INSERT INTO gold.articles (
            silver_article_id, version, source, source_id, headline, author_name,
            source_url, bucket_name, object_key, content_hash, content_size_bytes
        ) VALUES (
            v_silver_article_id, 1, 'folhapress', '9990001',
            'Matéria sintética para validação', NULL,
            'https://folhapress.example/texto/9990001', 'gold-approved',
            'folhapress/2026/09/23/9990001-v1.txt', repeat('a', 64), 512
        );
        RAISE EXCEPTION 'Gold sem autor deveria ser rejeitado';
    EXCEPTION WHEN not_null_violation THEN
        NULL;
    END;

    INSERT INTO gold.articles (
        silver_article_id, version, source, source_id, headline, author_name,
        source_url, bucket_name, object_key, content_hash, content_size_bytes
    ) VALUES (
        v_silver_article_id, 1, 'folhapress', '9990001',
        'Matéria sintética para validação', 'Autora Sintética',
        'https://folhapress.example/texto/9990001', 'gold-approved',
        'folhapress/2026/09/23/9990001-v1.txt', repeat('a', 64), 512
    ) RETURNING id INTO v_gold_article_id;

    BEGIN
        UPDATE gold.articles SET headline = 'Não permitido' WHERE id = v_gold_article_id;
        RAISE EXCEPTION 'O trigger de imutabilidade do Gold deveria ter rejeitado a alteração';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM NOT LIKE 'Gold é um snapshot imutável%' THEN
            RAISE;
        END IF;
    END;
END;
$$;
