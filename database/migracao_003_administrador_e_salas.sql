-- LivePresenceAI - Migração 003 (04/10/2026)
-- Aplicada automaticamente pelo backend (backend/migracoes.py). Mudanças em backend/models.py:
--   1. Perfil do usuário (administrador ou professor) e conta ativa/desativada.
--      Banco já em uso sem administrador: o professor mais antigo passa a administrador.
--   2. Salas de aula: cada computador com câmera atende uma sala; a turma pode ter uma sala padrão e
--      cada chamada registra a sala em que aconteceu.
-- Seguro para rodar mais de uma vez.

BEGIN;

ALTER TABLE professor ADD COLUMN IF NOT EXISTS perfil VARCHAR(20) NOT NULL DEFAULT 'professor';
ALTER TABLE professor ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE professor SET perfil = 'administrador'
 WHERE id = (SELECT min(id) FROM professor)
   AND NOT EXISTS (SELECT 1 FROM professor WHERE perfil = 'administrador');

CREATE TABLE IF NOT EXISTS sala (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(60) NOT NULL,
    criado_em TIMESTAMP,
    CONSTRAINT uq_sala_nome UNIQUE (nome)
);

ALTER TABLE turma ADD COLUMN IF NOT EXISTS sala_id INTEGER REFERENCES sala(id);
ALTER TABLE sessao ADD COLUMN IF NOT EXISTS sala_id INTEGER REFERENCES sala(id);

COMMIT;
