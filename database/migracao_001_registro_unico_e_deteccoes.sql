-- LivePresenceAI - Migração 001 (30/09/2026)
-- Aplica em bancos criados antes desta data as mudanças feitas em backend/models.py:
--   1. Um único registro de presença por aluno em cada sessão (UNIQUE).
--   2. Contador de detecções, usado no cálculo da confiança média aritmética.
-- Bancos novos já são criados assim pelo backend; neste caso, o script não faz nada.
-- Seguro para rodar mais de uma vez.

BEGIN;

ALTER TABLE registro_presenca
    ADD COLUMN IF NOT EXISTS numero_deteccoes INTEGER NOT NULL DEFAULT 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_registro_sessao_aluno'
          AND conrelid = 'registro_presenca'::regclass
    ) THEN
        ALTER TABLE registro_presenca
            ADD CONSTRAINT uq_registro_sessao_aluno UNIQUE (sessao_id, aluno_id);
    END IF;
END $$;

COMMIT;
