"""Autenticação, perfis e proteção contra tentativa de senhas."""
import main
from conftest import SENHA, cabecalho, novo_professor


def test_login_bloqueia_apos_tentativas_erradas(cliente, db):
    p = novo_professor(db)
    for _ in range(main.LOGIN_TENTATIVAS_MAX):
        assert cliente.post("/login", data={"username": p.email, "password": "errada"}).status_code == 401
    r = cliente.post("/login", data={"username": p.email, "password": SENHA})
    assert r.status_code == 429 and "Aguarde" in r.json()["detail"]  # bloqueado mesmo com a senha certa
    outro = novo_professor(db)
    assert cliente.post("/login", data={"username": outro.email, "password": SENHA}).status_code == 200


def test_acerto_zera_o_contador_do_email(cliente, db):
    p = novo_professor(db)
    for _ in range(main.LOGIN_TENTATIVAS_MAX - 1):
        cliente.post("/login", data={"username": p.email, "password": "errada"})
    assert cliente.post("/login", data={"username": p.email, "password": SENHA}).status_code == 200
    assert cliente.post("/login", data={"username": p.email, "password": "errada"}).status_code == 401


def test_rota_protegida_exige_token(cliente):
    assert cliente.get("/turmas").status_code == 401


def test_rn14_professor_nao_cadastra_professor(cliente, db):
    p = novo_professor(db)
    r = cliente.post("/professores", headers=cabecalho(cliente, p.email),
                     json={"nome": "X", "email": "x@teste.local", "senha": "senha-forte-1"})
    assert r.status_code == 403


def test_rn14_conta_desativada_nao_entra(cliente, db):
    p = novo_professor(db)
    p.ativo = False
    db.commit()
    assert cliente.post("/login", data={"username": p.email, "password": SENHA}).status_code == 401


def test_rn11_ra_unico(cliente, db):
    p = novo_professor(db)
    H = cabecalho(cliente, p.email)
    t = cliente.post("/turmas", headers=H, json={"nome": "RA"}).json()
    assert cliente.post(f"/turmas/{t['id']}/alunos", headers=H, json={"nome": "A", "ra": "PYRA1"}).status_code == 201
    assert cliente.post(f"/turmas/{t['id']}/alunos", headers=H, json={"nome": "B", "ra": "pyra1"}).status_code == 409
