-- LivePresenceAI - Schema PostgreSQL (v1 - MVP)
CREATE TABLE professor (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE turma (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    professor_id INTEGER NOT NULL REFERENCES professor(id),
    criado_em TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE aluno (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    turma_id INTEGER NOT NULL REFERENCES turma(id),
    embedding JSONB,
    criado_em TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE sessao (
    id SERIAL PRIMARY KEY,
    turma_id INTEGER NOT NULL REFERENCES turma(id),
    professor_id INTEGER NOT NULL REFERENCES professor(id),
    inicio TIMESTAMP NOT NULL DEFAULT now(),
    fim TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'aberta'
);

CREATE TABLE registro_presenca (
    id SERIAL PRIMARY KEY,
    sessao_id INTEGER NOT NULL REFERENCES sessao(id),
    aluno_id INTEGER NOT NULL REFERENCES aluno(id),
    entrada TIMESTAMP NOT NULL,
    ultima_visualizacao TIMESTAMP NOT NULL,
    tempo_total_presente INTERVAL,
    confianca_media NUMERIC(5,2),
    numero_deteccoes INTEGER NOT NULL DEFAULT 1,
    percentual_presenca NUMERIC(5,2),
    CONSTRAINT uq_registro_sessao_aluno UNIQUE (sessao_id, aluno_id)
);

CREATE INDEX idx_registro_sessao ON registro_presenca(sessao_id);
CREATE INDEX idx_aluno_turma ON aluno(turma_id);
