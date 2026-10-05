-- LivePresenceAI - Migração 002 (04/10/2026)
-- Aplica em bancos criados antes desta data as mudanças feitas em backend/models.py:
--   1. RA do aluno, único no sistema (cada aluno pertence a um curso e a uma turma).
--      Alunos já existentes ficam sem RA até serem editados na tela de gestão do app.
--   2. Data e hora (UTC) do consentimento com o cadastro facial (LGPD, art. 11).
--   3. "Sem cadastro facial" gravado como o valor JSON null passa a ser NULL do SQL.
-- Bancos novos já são criados assim pelo backend; neste caso, o script não faz nada.
-- Seguro para rodar mais de uma vez.

BEGIN;

ALTER TABLE aluno ADD COLUMN IF NOT EXISTS ra VARCHAR(20);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_aluno_ra'
          AND conrelid = 'aluno'::regclass
    ) THEN
        ALTER TABLE aluno ADD CONSTRAINT uq_aluno_ra UNIQUE (ra);
    END IF;
END $$;

ALTER TABLE aluno ADD COLUMN IF NOT EXISTS consentimento_biometrico_em TIMESTAMP;

UPDATE aluno SET embedding = NULL WHERE embedding::text = 'null';

COMMIT;
