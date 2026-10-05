"""
LivePresenceAI - Preparo automatico do banco de dados.

Ao iniciar, o backend:
  1. cria as tabelas que ainda nao existem (create_all, com a estrutura atual dos modelos);
  2. aplica, em ordem numerica, os scripts database/migracao_NNN_*.sql que ainda nao constam na tabela
     versao_schema, registrando cada um.

Os scripts sao idempotentes (podem rodar em banco novo ou ja migrado a mao) e cada um roda na propria
transacao (BEGIN/COMMIT do arquivo). Uma trava do PostgreSQL (pg_advisory_lock) impede que dois processos
migrem ao mesmo tempo. Assim a instalacao e as atualizacoes nao exigem mais rodar SQL no pgAdmin.
"""
import os
import re
from typing import List, Tuple

from sqlalchemy.engine import Engine

PASTA_MIGRACOES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database")
PADRAO = re.compile(r"^migracao_(\d{3})_.+\.sql$")
TRAVA = 4815162342  # identificador arbitrario da trava de migracao


def migracoes_disponiveis(pasta: str = PASTA_MIGRACOES) -> List[Tuple[int, str]]:
    encontradas = []
    for nome in os.listdir(pasta):
        casamento = PADRAO.match(nome)
        if casamento:
            encontradas.append((int(casamento.group(1)), nome))
    return sorted(encontradas)


def preparar_banco(engine: Engine, base, pasta: str = PASTA_MIGRACOES) -> List[str]:
    """Cria tabelas que faltam e aplica as migracoes pendentes. Devolve os nomes aplicados agora."""
    base.metadata.create_all(bind=engine)
    aplicadas_agora = []
    conexao = engine.raw_connection()
    try:
        conexao.autocommit = True  # cada script controla a propria transacao
        cursor = conexao.cursor()
        cursor.execute("SELECT pg_advisory_lock(%s)", (TRAVA,))
        try:
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS versao_schema ("
                " versao INTEGER PRIMARY KEY,"
                " arquivo VARCHAR(200) NOT NULL,"
                " aplicada_em TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'))"
            )
            cursor.execute("SELECT versao FROM versao_schema")
            ja_aplicadas = {linha[0] for linha in cursor.fetchall()}
            for versao, arquivo in migracoes_disponiveis(pasta):
                if versao in ja_aplicadas:
                    continue
                with open(os.path.join(pasta, arquivo), encoding="utf-8") as script:
                    cursor.execute(script.read())
                cursor.execute("INSERT INTO versao_schema (versao, arquivo) VALUES (%s, %s)", (versao, arquivo))
                aplicadas_agora.append(arquivo)
                print(f"Migracao aplicada: {arquivo}")
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (TRAVA,))
    finally:
        conexao.close()
    return aplicadas_agora
