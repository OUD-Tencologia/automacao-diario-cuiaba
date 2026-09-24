-- Esta migration introduz conteúdo editorial persistente. Um rollback por
-- DROP destruiria notícias e não é permitido; restaure backup validado.
DO $$
BEGIN
    RAISE EXCEPTION
        'Rollback automático da Gold única é bloqueado para preservar conteúdo editorial';
END;
$$;
