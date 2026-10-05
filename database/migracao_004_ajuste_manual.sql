-- LivePresenceAI - Migração 004 (05/10/2026)
-- Aplicada automaticamente pelo backend (backend/migracoes.py).
-- Ajuste manual da chamada (RN-15): o professor marca presença ou falta de um aluno numa aula, com motivo
-- (ex.: aluno sem autorização de biometria, câmera não reconheceu, falta justificada). O ajuste prevalece
-- sobre o cálculo automático, que continua guardado em registro_presenca para auditoria.
-- Seguro para rodar mais de uma vez.

BEGIN;

CREATE TABLE IF NOT EXISTS ajuste_presenca (
    id SERIAL PRIMARY KEY,
    sessao_id INTEGER NOT NULL REFERENCES sessao(id),
    aluno_id INTEGER NOT NULL REFERENCES aluno(id),
    situacao VARCHAR(10) NOT NULL,
    motivo VARCHAR(200) NOT NULL,
    professor_id INTEGER NOT NULL REFERENCES professor(id),
    criado_em TIMESTAMP NOT NULL,
    CONSTRAINT uq_ajuste_sessao_aluno UNIQUE (sessao_id, aluno_id),
    CONSTRAINT ck_ajuste_situacao CHECK (situacao IN ('presenca', 'falta'))
);

COMMIT;
