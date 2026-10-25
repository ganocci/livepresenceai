"""
Suíte pytest do backend: roda sem servidor ligado (TestClient do FastAPI) num schema temporário do PostgreSQL,
criado no início e apagado no fim. O banco de desenvolvimento não é alterado.

Uso (na pasta backend, com o venv):  python -m pytest
Banco: DATABASE_URL_TESTES (padrão: o banco de desenvolvimento na porta 5433, só para criar o schema temporário).
"""
import os
import secrets
import sys

import pytest
from sqlalchemy import create_engine, text

BASE = os.getenv("DATABASE_URL_TESTES",
                 "postgresql+psycopg2://livepresenceai:livepresenceai@localhost:5433/livepresenceai")
SCHEMA = f"pytest_{secrets.token_hex(4)}"

# O backend lê a configuração ao ser importado: o schema precisa existir antes do "import main"
_motor_admin = create_engine(BASE)
with _motor_admin.begin() as c:
    c.execute(text(f"CREATE SCHEMA {SCHEMA}"))
separador = "&" if "?" in BASE else "?"
os.environ["DATABASE_URL"] = f"{BASE}{separador}options=-csearch_path%3D{SCHEMA}"
os.environ["CHAVE_MODULO_IA"] = "chave-pytest"
os.environ["SECRET_KEY_JWT"] = "segredo-pytest"
os.environ["LIVEPRESENCEAI_DESCOBERTA"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from models import Aluno, Professor, Sala, Turma  # noqa: E402

CHAVE_IA = {"X-API-Key": "chave-pytest"}
SENHA = "senha-pytest-123"


def pytest_sessionfinish(session, exitstatus):
    main.engine.dispose()
    with _motor_admin.begin() as c:
        c.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
    _motor_admin.dispose()


@pytest.fixture
def db():
    sessao = SessionLocal()
    yield sessao
    sessao.close()


@pytest.fixture
def cliente():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def limpar_estado_em_memoria():
    main._erros_login.clear()
    main._contatos_ia.clear()
    yield


def novo_professor(db, perfil="professor"):
    p = Professor(nome="Prof Teste", email=f"p_{secrets.token_hex(4)}@teste.local",
                  senha_hash=main.pwd_context.hash(SENHA), perfil=perfil)
    db.add(p)
    db.commit()
    return p


def cabecalho(cliente, email, senha=SENHA):
    r = cliente.post("/login", data={"username": email, "password": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def cenario(db, cliente):
    """Professor com uma turma de três alunos (dois com autorização de biometria) e uma sala."""
    prof = novo_professor(db)
    sala = Sala(nome=f"Sala {secrets.token_hex(3)}")
    db.add(sala)
    db.commit()
    turma = Turma(nome="Turma pytest", professor_id=prof.id, sala_id=sala.id)
    db.add(turma)
    db.commit()
    alunos = []
    for i, autorizado in enumerate((True, True, False)):
        a = Aluno(nome=f"Aluno {i}", ra=f"PY{secrets.token_hex(3).upper()}{i}", turma_id=turma.id,
                  embedding=[1.0 / 512 ** 0.5] * 512 if autorizado else None,
                  consentimento_biometrico_em=main.datetime.utcnow() if autorizado else None)
        db.add(a)
        alunos.append(a)
    db.commit()
    return {"prof": prof, "turma": turma, "sala": sala, "alunos": alunos, "H": cabecalho(cliente, prof.email)}
